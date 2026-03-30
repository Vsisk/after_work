from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

from billing_dsl_agent.log_utils import dumps_for_log, get_logger
from billing_dsl_agent.llm_planner_models import (
    AllowedNodeType,
    AllowedQueryKind,
    BasePlan,
    BasePlanInput,
    BOSelectionTerm,
    ComplexityLevel,
    DefinitionKind,
    FieldConstraintTerm,
    FilteredPlanSpec,
    FilteredPlanSpecInput,
    FilteredResourceBundle,
    FinalPlanInput,
    InternalFinalPlan,
    PlannerDiagnostics,
    ResourceRefTerm,
    ReturnShape,
    StageError,
)
from billing_dsl_agent.models import (
    BinaryOpPlanNode,
    ContextRefPlanNode,
    ExprPlanNode,
    FilteredEnvironment,
    FunctionCallPlanNode,
    LLMAttemptRecord,
    LLMErrorRecord,
    LiteralPlanNode,
    LocalRefPlanNode,
    NodeDef,
    PlanDiagnostic,
    ProgramPlan,
    ProgramPlanLimits,
    QueryCallPlanNode,
    UnaryOpPlanNode,
    ValidationIssue,
)
from billing_dsl_agent.plan_validator import (
    collect_context_refs,
    collect_function_refs,
    collect_local_refs,
    collect_query_refs,
    count_expr_nodes,
    count_if_nodes,
    parse_program_plan_payload,
    validate_program_plan_structure,
)
from billing_dsl_agent.services.llm_client import OpenAILLMClient, StructuredExecutionResult

logger = get_logger(__name__)

SUPPORTED_NODE_TYPES: list[AllowedNodeType] = [
    AllowedNodeType.LITERAL,
    AllowedNodeType.CONTEXT_REF,
    AllowedNodeType.LOCAL_REF,
    AllowedNodeType.VAR_REF,
    AllowedNodeType.QUERY_CALL,
    AllowedNodeType.FUNCTION_CALL,
    AllowedNodeType.IF,
    AllowedNodeType.BINARY_OP,
    AllowedNodeType.UNARY_OP,
    AllowedNodeType.FIELD_ACCESS,
    AllowedNodeType.INDEX_ACCESS,
    AllowedNodeType.LIST_LITERAL,
]
SUPPORTED_QUERY_KINDS: list[AllowedQueryKind] = [
    AllowedQueryKind.SELECT_ONE,
    AllowedQueryKind.FETCH_ONE,
    AllowedQueryKind.SELECT,
    AllowedQueryKind.FETCH,
]
STAGE1_PROMPT_KEY = "dsl_base_plan_prompt"
STAGE3_PROMPT_KEY = "dsl_final_plan_prompt"
STAGE1_PROMPT_VERSION = "base-plan-v1"
STAGE3_PROMPT_VERSION = "final-plan-v1"

T = TypeVar("T")


class PlannerSkeletonPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class PlannerDetailPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass(slots=True)
class PlannerStageResult(Generic[T]):
    success: bool
    payload: T | None = None
    errors: list[LLMErrorRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] | None = None


def _sorted_unique(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _sorted_allowed_query_kinds(values: list[AllowedQueryKind]) -> list[AllowedQueryKind]:
    seen: set[AllowedQueryKind] = set()
    ordered: list[AllowedQueryKind] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _sorted_allowed_node_types(values: list[AllowedNodeType]) -> list[AllowedNodeType]:
    seen: set[AllowedNodeType] = set()
    ordered: list[AllowedNodeType] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _context_ref_aliases(path: str) -> set[str]:
    aliases = {path}
    if path.startswith("$ctx$.root."):
        aliases.add("$ctx$." + path[len("$ctx$.root.") :])
    elif path.startswith("$ctx$."):
        aliases.add("$ctx$.root." + path[len("$ctx$.") :])
    return aliases


def _allowed_node_type_from_name(node_type: str) -> AllowedNodeType | None:
    for item in SUPPORTED_NODE_TYPES:
        if item.value == node_type:
            return item
    return None


def _child_expressions(node: ExprPlanNode) -> list[ExprPlanNode]:
    children: list[ExprPlanNode] = []
    if isinstance(node, QueryCallPlanNode):
        if node.where is not None:
            children.append(node.where)
        children.extend(filter_item.value for filter_item in node.filters)
        children.extend(pair.value for pair in node.pairs)
        return children
    if isinstance(node, FunctionCallPlanNode):
        return list(node.args)
    if isinstance(node, BinaryOpPlanNode):
        return [node.left, node.right]
    if isinstance(node, UnaryOpPlanNode):
        return [node.operand]
    if hasattr(node, "condition") and hasattr(node, "then_expr") and hasattr(node, "else_expr"):
        return [node.condition, node.then_expr, node.else_expr]
    if hasattr(node, "base") and hasattr(node, "field"):
        return [node.base]
    if hasattr(node, "base") and hasattr(node, "index"):
        return [node.base, node.index]
    if hasattr(node, "items"):
        return list(node.items)
    return children


def _collect_node_types(node: ExprPlanNode) -> list[AllowedNodeType]:
    current = _allowed_node_type_from_name(getattr(node, "type", ""))
    collected: list[AllowedNodeType] = [current] if current is not None else []
    for child in _child_expressions(node):
        collected.extend(_collect_node_types(child))
    return collected


def _infer_return_shape(expr: ExprPlanNode) -> ReturnShape:
    if isinstance(expr, LiteralPlanNode):
        return ReturnShape.LITERAL_VALUE
    if isinstance(expr, (ContextRefPlanNode, LocalRefPlanNode)) or getattr(expr, "type", "") == "var_ref":
        return ReturnShape.DIRECT_REF
    if isinstance(expr, QueryCallPlanNode):
        return ReturnShape.QUERY_RESULT
    if isinstance(expr, FunctionCallPlanNode):
        return ReturnShape.FUNCTION_RESULT
    if getattr(expr, "type", "") == "if":
        return ReturnShape.CONDITIONAL_RESULT
    if getattr(expr, "type", "") in {"list_literal", "index_access"}:
        return ReturnShape.LIST_RESULT
    if getattr(expr, "type", "") == "field_access":
        return ReturnShape.OBJECT_FIELD
    return ReturnShape.UNKNOWN


@dataclass(slots=True)
class StubOpenAIClient:
    repair_response: Optional[Dict[str, Any]] = None
    stage_responses: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_payload: Optional[Dict[str, Any]] = None

    def execute_structured(
        self,
        *,
        prompt_key: str,
        lang: str,
        prompt_params: Dict[str, Any] | None,
        response_model: Any,
        stage: str,
        attempt_index: int = 1,
        response_parser: Any = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[Any]:
        payload = dict(prompt_params or {})
        self.last_payload = payload
        logger.info(
            "stub_llm_request stage=%s attempt=%s prompt_key=%s payload=%s",
            stage,
            attempt_index,
            prompt_key,
            dumps_for_log(payload),
        )
        if stage in self.stage_responses:
            raw_response = self.stage_responses[stage]
        elif stage == "repair":
            raw_response = self.repair_response
        else:
            raw_response = None
        parsed = None
        errors: list[LLMErrorRecord] = []
        if raw_response is not None:
            try:
                if response_parser is not None:
                    parsed = response_parser(raw_response)
                elif response_model is not None:
                    parsed = response_model.model_validate(raw_response)
            except Exception as exc:  # pragma: no cover - parity with real client schema failure handling
                errors.append(
                    LLMErrorRecord(
                        stage=stage,
                        code="response_schema_error",
                        message=str(exc),
                        raw_payload=raw_response if isinstance(raw_response, dict) else None,
                        exception_type=type(exc).__name__,
                    )
                )
        logger.info(
            "stub_llm_response stage=%s attempt=%s response=%s errors=%s",
            stage,
            attempt_index,
            dumps_for_log(raw_response),
            [item.code for item in errors],
        )
        return StructuredExecutionResult(
            parsed=parsed,
            errors=errors,
            raw_payload=raw_response,
            attempt=LLMAttemptRecord(
                stage=stage,
                attempt_index=attempt_index,
                request_payload=payload,
                response_payload=raw_response,
                parsed_ok=parsed is not None and not errors,
                errors=errors,
            ),
        )

class LLMPlanner:
    def __init__(
        self,
        client: OpenAILLMClient | StubOpenAIClient,
        prompt_manager: Optional[Any] = None,
        prompt_lang: str = "en",
    ):
        self.client = client
        self.prompt_lang = prompt_lang
        if prompt_manager is not None and hasattr(self.client, "prompt_manager"):
            self.client.prompt_manager = prompt_manager
        self.plan_attempts: list[LLMAttemptRecord] = []
        self.repair_attempts: list[LLMAttemptRecord] = []
        self.llm_errors: list[LLMErrorRecord] = []
        self.planner_diagnostics = PlannerDiagnostics()

    def plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> ProgramPlan:
        self.plan_attempts = []
        self.repair_attempts = []
        self.llm_errors = []
        self.planner_diagnostics = PlannerDiagnostics()
        logger.info(
            "planner_started user_requirement=%s node_id=%s node_path=%s",
            user_requirement,
            node_def.node_id,
            node_def.node_path,
        )

        base_input = self._build_base_plan_input(user_requirement=user_requirement, node_def=node_def, env=env)
        stage1_result = self._run_stage1_base_plan(base_input)
        if not stage1_result.success or stage1_result.payload is None:
            logger.warning(
                "planner_stage_failed stage=plan_base errors=%s",
                [item.code for item in stage1_result.errors],
            )
            return self._failed_plan(
                raw_plan=stage1_result.raw_response,
                default_code="stage1_base_plan_failed",
                errors=stage1_result.errors,
            )
        logger.info(
            "planner_stage_completed stage=plan_base payload=%s",
            dumps_for_log(stage1_result.payload),
        )

        spec_input = self._build_filtered_spec_input(base_plan=stage1_result.payload, planner_limits=base_input.planner_runtime_limits)
        spec_result = self._build_filtered_spec(spec_input)
        if not spec_result.success or spec_result.payload is None:
            logger.warning(
                "planner_stage_failed stage=plan_spec errors=%s",
                [item.code for item in spec_result.errors],
            )
            return self._failed_plan(
                raw_plan=spec_result.raw_response,
                default_code="stage2_filtered_spec_failed",
                errors=spec_result.errors,
            )
        logger.info(
            "planner_stage_completed stage=plan_spec payload=%s",
            dumps_for_log(spec_result.payload),
        )

        final_input = self._build_final_plan_input(
            user_requirement=user_requirement,
            node_def=node_def,
            env=env,
            base_plan=stage1_result.payload,
            filtered_spec=spec_result.payload,
            runtime_limits=base_input.planner_runtime_limits,
        )
        stage3_result = self._run_stage3_final_plan(final_input)
        if not stage3_result.success or stage3_result.payload is None:
            logger.warning(
                "planner_stage_failed stage=plan_final errors=%s",
                [item.code for item in stage3_result.errors],
            )
            return self._failed_plan(
                raw_plan=stage3_result.raw_response,
                default_code="stage3_final_plan_failed",
                errors=stage3_result.errors,
            )

        logger.info(
            "planner_stage_completed stage=plan_final payload=%s",
            dumps_for_log(stage3_result.payload),
        )
        return self._adapt_internal_final_plan_to_program_plan(stage3_result.payload)

    def repair(
        self,
        invalid_plan: ProgramPlan,
        env: FilteredEnvironment,
        issues: list[ValidationIssue],
    ) -> Optional[ProgramPlan]:
        env_payload = self._build_env_payload(env)
        invalid_plan_payload = invalid_plan.raw_plan or invalid_plan.model_dump(mode="python")
        issues_payload = [item.model_dump(mode="python") for item in issues]
        prior_errors_payload = [item.model_dump(mode="python") for item in self.llm_errors]
        logger.info(
            "planner_repair_started issues=%s invalid_plan=%s",
            dumps_for_log(issues_payload),
            dumps_for_log(invalid_plan_payload),
        )
        execution = self.client.execute_structured(
            prompt_key="dsl_repair_prompt",
            lang=self.prompt_lang,
            prompt_params={
                "invalid_plan_json": json.dumps(invalid_plan_payload, ensure_ascii=False),
                "issues_json": json.dumps(issues_payload, ensure_ascii=False),
                "environment_json": json.dumps(env_payload, ensure_ascii=False),
                "prior_errors_json": json.dumps(prior_errors_payload, ensure_ascii=False),
                "invalid_plan": invalid_plan_payload,
                "issues": issues_payload,
                "environment": env_payload,
                "prior_errors": prior_errors_payload,
            },
            response_model=ProgramPlan,
            response_parser=parse_program_plan_payload,
            stage="repair",
            attempt_index=len(self.repair_attempts) + 1,
        )
        self.repair_attempts.append(execution.attempt)
        self.llm_errors.extend(execution.errors)
        logger.info(
            "planner_repair_completed parsed=%s error_codes=%s",
            execution.parsed is not None,
            [item.code for item in execution.errors],
        )
        return execution.parsed

    def _build_base_plan_input(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> BasePlanInput:
        candidate_contexts = [
            ResourceRefTerm(
                resource_id=item.resource_id,
                ref=item.path,
                label=item.name,
                description=item.description,
                category="global_context",
            )
            for item in env.selected_global_contexts
        ]
        candidate_contexts.extend(
            ResourceRefTerm(
                resource_id=item.resource_id,
                ref=item.access_path,
                label=item.property_name,
                description=item.annotation,
                category="local_context",
            )
            for item in env.visible_local_context.ordered_nodes
        )
        candidate_bos = [
            BOSelectionTerm(
                bo_id=item.resource_id,
                bo_name=item.bo_name,
                field_ids=list(item.field_ids),
                naming_sql_ids=list(item.naming_sql_ids),
                data_source=item.data_source,
                available_query_kinds=self._available_query_kinds_for_bo(item.field_ids, item.naming_sql_ids),
            )
            for item in env.selected_bos
        ]
        candidate_functions = [
            ResourceRefTerm(
                resource_id=item.resource_id,
                ref=item.function_id,
                label=item.full_name,
                description=item.description,
                category="function",
            )
            for item in env.selected_functions
        ]
        return BasePlanInput(
            user_query=user_requirement,
            node_info=node_def,
            candidate_contexts=candidate_contexts,
            candidate_bos=candidate_bos,
            candidate_functions=candidate_functions,
            planner_runtime_limits=ProgramPlanLimits(),
            legacy_hints={},
        )

    def _run_stage1_base_plan(self, base_input: BasePlanInput) -> PlannerStageResult[BasePlan]:
        return self._execute_stage_with_retry(
            stage_name="plan_base",
            prompt_key=STAGE1_PROMPT_KEY,
            prompt_version=STAGE1_PROMPT_VERSION,
            response_model=BasePlan,
            response_parser=self._parse_base_plan_payload,
            prompt_params_builder=lambda retry_guidance: self._build_stage1_prompt_params(base_input, retry_guidance),
            validator=lambda payload: self._validate_stage1_base_plan(payload, base_input),
        )

    def _build_filtered_spec_input(self, *, base_plan: BasePlan, planner_limits: ProgramPlanLimits) -> FilteredPlanSpecInput:
        return FilteredPlanSpecInput(
            base_plan=base_plan,
            planner_limits=planner_limits,
            global_supported_node_types=list(SUPPORTED_NODE_TYPES),
            global_supported_query_kinds=list(SUPPORTED_QUERY_KINDS),
        )

    def _build_filtered_spec(self, spec_input: FilteredPlanSpecInput) -> PlannerStageResult[FilteredPlanSpec]:
        base_plan = spec_input.base_plan
        allowed_node_types = [item for item in base_plan.allowed_node_types if item in spec_input.global_supported_node_types]
        allow_definitions = base_plan.plan_shape.needs_definitions
        if not base_plan.definition_hints and base_plan.plan_shape.estimated_complexity == ComplexityLevel.LOW:
            allow_definitions = False
        if not allow_definitions:
            allowed_node_types = [item for item in allowed_node_types if item != AllowedNodeType.VAR_REF]

        if not base_plan.plan_shape.needs_query:
            allowed_node_types = [item for item in allowed_node_types if item != AllowedNodeType.QUERY_CALL]
            allowed_query_kinds: list[AllowedQueryKind] = []
        else:
            allowed_query_kinds = self._shrink_query_kinds(base_plan)

        if not base_plan.plan_shape.needs_function_call or not base_plan.required_resources.function_refs:
            allowed_node_types = [item for item in allowed_node_types if item != AllowedNodeType.FUNCTION_CALL]
        if not base_plan.plan_shape.needs_condition:
            allowed_node_types = [item for item in allowed_node_types if item != AllowedNodeType.IF]
        if base_plan.return_shape != ReturnShape.LIST_RESULT:
            allowed_node_types = [item for item in allowed_node_types if item not in {AllowedNodeType.LIST_LITERAL, AllowedNodeType.INDEX_ACCESS}]
        if not base_plan.required_resources.bo_refs:
            allowed_node_types = [item for item in allowed_node_types if item != AllowedNodeType.QUERY_CALL]
            allowed_query_kinds = []

        allowed_node_types = _sorted_allowed_node_types(allowed_node_types)
        if not allowed_node_types:
            allowed_node_types = [AllowedNodeType.LITERAL]

        limits = spec_input.planner_limits
        if allow_definitions:
            if base_plan.plan_shape.estimated_complexity == ComplexityLevel.LOW:
                max_definitions = min(limits.max_definitions, max(1, len(base_plan.definition_hints)))
                max_total_nodes = min(limits.max_total_expr_nodes, 18)
                max_return_depth = min(limits.max_return_expr_depth, 3)
            elif base_plan.plan_shape.estimated_complexity == ComplexityLevel.MEDIUM:
                max_definitions = min(limits.max_definitions, max(2, len(base_plan.definition_hints) or 2))
                max_total_nodes = min(limits.max_total_expr_nodes, 28)
                max_return_depth = min(limits.max_return_expr_depth, 4)
            else:
                max_definitions = min(limits.max_definitions, max(3, len(base_plan.definition_hints) or 3))
                max_total_nodes = min(limits.max_total_expr_nodes, 40)
                max_return_depth = limits.max_return_expr_depth
            max_definition_depth = limits.max_expr_depth_per_definition
            allowed_definition_kinds = [DefinitionKind.VARIABLE]
        else:
            max_definitions = 0
            max_definition_depth = 0
            if base_plan.plan_shape.estimated_complexity == ComplexityLevel.LOW:
                max_return_depth = min(limits.max_return_expr_depth, 3)
                max_total_nodes = min(limits.max_total_expr_nodes, 14)
            elif base_plan.plan_shape.estimated_complexity == ComplexityLevel.MEDIUM:
                max_return_depth = min(limits.max_return_expr_depth, 4)
                max_total_nodes = min(limits.max_total_expr_nodes, 24)
            else:
                max_return_depth = limits.max_return_expr_depth
                max_total_nodes = min(limits.max_total_expr_nodes, 32)
            allowed_definition_kinds = []

        allowed_return_shapes = [base_plan.return_shape] if base_plan.return_shape != ReturnShape.UNKNOWN else [ReturnShape.LITERAL_VALUE, ReturnShape.DIRECT_REF]
        allowed_binary_operators = (
            ["==", "!=", ">", ">=", "<", "<=", "and", "or", "+", "-", "*", "/", "%"]
            if base_plan.plan_shape.needs_condition
            else ["+", "-", "*", "/", "%"]
        )
        allowed_unary_operators = ["not", "-"] if base_plan.plan_shape.needs_condition else ["-"]

        spec = FilteredPlanSpec(
            allowed_definition_kinds=allowed_definition_kinds,
            allowed_node_types=allowed_node_types,
            allowed_query_kinds=allowed_query_kinds,
            allow_definitions=allow_definitions,
            max_definitions=max_definitions,
            max_expr_depth_per_definition=max_definition_depth,
            max_return_expr_depth=max_return_depth,
            max_total_expr_nodes=max_total_nodes,
            allowed_return_shapes=allowed_return_shapes,
            field_constraints=self._build_field_constraints(
                allowed_node_types=allowed_node_types,
                allowed_query_kinds=allowed_query_kinds,
                allow_definitions=allow_definitions,
                max_definitions=max_definitions,
                allowed_return_shapes=allowed_return_shapes,
                allowed_binary_operators=allowed_binary_operators,
                allowed_unary_operators=allowed_unary_operators,
            ),
            example_output_skeleton=self._build_final_plan_skeleton(
                base_plan=base_plan,
                allowed_node_types=allowed_node_types,
                allow_definitions=allow_definitions,
            ),
            final_plan_schema_version="final-plan-v1",
            allowed_binary_operators=allowed_binary_operators if AllowedNodeType.BINARY_OP in allowed_node_types else [],
            allowed_unary_operators=allowed_unary_operators if AllowedNodeType.UNARY_OP in allowed_node_types else [],
        )
        validation_errors = self._validate_stage2_filtered_spec(spec, base_plan)
        if validation_errors:
            self._record_stage_error(
                stage_name="build_filtered_spec",
                prompt_key="deterministic_builder",
                prompt_version="filtered-spec-v1",
                raw_output=spec.model_dump(mode="python"),
                validation_error="; ".join(validation_errors),
            )
            return PlannerStageResult(
                success=False,
                errors=[self._make_llm_error("build_filtered_spec", "stage_validation_error", "; ".join(validation_errors), spec.model_dump(mode="python"))],
                raw_response=spec.model_dump(mode="python"),
            )
        self.planner_diagnostics.stage_trace.append("build_filtered_spec")
        return PlannerStageResult(success=True, payload=spec, raw_response=spec.model_dump(mode="python"))

    def _build_final_plan_input(
        self,
        *,
        user_requirement: str,
        node_def: NodeDef,
        env: FilteredEnvironment,
        base_plan: BasePlan,
        filtered_spec: FilteredPlanSpec,
        runtime_limits: ProgramPlanLimits,
    ) -> FinalPlanInput:
        contexts_by_id = {
            item.resource_id: ResourceRefTerm(
                resource_id=item.resource_id,
                ref=item.path,
                label=item.name,
                description=item.description,
                category="global_context",
            )
            for item in env.selected_global_contexts
        }
        contexts_by_id.update(
            {
                item.resource_id: ResourceRefTerm(
                    resource_id=item.resource_id,
                    ref=item.access_path,
                    label=item.property_name,
                    description=item.annotation,
                    category="local_context",
                )
                for item in env.visible_local_context.ordered_nodes
            }
        )
        functions_by_id = {
            item.resource_id: ResourceRefTerm(
                resource_id=item.resource_id,
                ref=item.function_id,
                label=item.full_name,
                description=item.description,
                category="function",
            )
            for item in env.selected_functions
        }
        return FinalPlanInput(
            user_query=user_requirement,
            node_info=node_def,
            base_plan=base_plan,
            filtered_spec=filtered_spec,
            filtered_resources=FilteredResourceBundle(
                context_refs=[
                    contexts_by_id[resource_id]
                    for resource_id in base_plan.required_resources.context_refs
                    if resource_id in contexts_by_id
                ],
                bo_refs=list(base_plan.required_resources.bo_refs),
                function_refs=[
                    functions_by_id[resource_id]
                    for resource_id in base_plan.required_resources.function_refs
                    if resource_id in functions_by_id
                ],
            ),
            runtime_limits=runtime_limits,
        )

    def _run_stage3_final_plan(self, final_input: FinalPlanInput) -> PlannerStageResult[InternalFinalPlan]:
        return self._execute_stage_with_retry(
            stage_name="plan_final",
            prompt_key=STAGE3_PROMPT_KEY,
            prompt_version=STAGE3_PROMPT_VERSION,
            response_model=InternalFinalPlan,
            response_parser=self._parse_internal_final_plan_payload,
            prompt_params_builder=lambda retry_guidance: self._build_stage3_prompt_params(final_input, retry_guidance),
            validator=lambda payload: self._validate_stage3_final_plan(
                payload,
                final_input.filtered_spec,
                final_input.base_plan,
                final_input,
            ),
        )

    def _adapt_internal_final_plan_to_program_plan(self, final_plan: InternalFinalPlan) -> ProgramPlan:
        raw_plan = final_plan.raw_plan or final_plan.model_dump(mode="python")
        return ProgramPlan(
            definitions=list(final_plan.definitions),
            return_expr=final_plan.return_expr,
            raw_plan=raw_plan,
            diagnostics=list(final_plan.diagnostics),
        )

    def _execute_stage_with_retry(
        self,
        *,
        stage_name: str,
        prompt_key: str,
        prompt_version: str,
        response_model: type[BaseModel],
        response_parser: Callable[[dict[str, Any]], T],
        prompt_params_builder: Callable[[str], dict[str, Any]],
        validator: Callable[[T], list[str]],
    ) -> PlannerStageResult[T]:
        retry_guidance = ""
        last_raw_response: dict[str, Any] | None = None
        last_errors: list[LLMErrorRecord] = []
        for attempt_index in (1, 2):
            prompt_params = prompt_params_builder(retry_guidance)
            execution = self.client.execute_structured(
                prompt_key=prompt_key,
                lang=self.prompt_lang,
                prompt_params=prompt_params,
                response_model=response_model,
                response_parser=response_parser,
                stage=stage_name,
                attempt_index=attempt_index,
            )
            self.plan_attempts.append(execution.attempt)
            self.llm_errors.extend(execution.errors)
            self.planner_diagnostics.stage_trace.append(stage_name)
            last_raw_response = execution.raw_payload
            last_errors = list(execution.errors)

            if execution.parsed is None:
                parse_error = "; ".join(item.message for item in execution.errors) or "stage parse failed"
                if attempt_index == 1:
                    retry_guidance = self._build_retry_prompt_for_stage(stage_name, parse_error=parse_error, validation_errors=[])
                    continue
                self._record_stage_error(
                    stage_name=stage_name,
                    prompt_key=prompt_key,
                    prompt_version=prompt_version,
                    raw_output=execution.raw_payload,
                    parse_error=parse_error,
                    retry_count=1,
                )
                return PlannerStageResult(success=False, errors=execution.errors, raw_response=execution.raw_payload)

            validation_errors = validator(execution.parsed)
            if not validation_errors:
                return PlannerStageResult(success=True, payload=execution.parsed, raw_response=execution.raw_payload)

            validation_error_text = "; ".join(validation_errors)
            last_errors = [
                *execution.errors,
                self._make_llm_error(stage_name, "stage_validation_error", validation_error_text, execution.raw_payload),
            ]
            self.llm_errors.extend(last_errors[len(execution.errors) :])
            if attempt_index == 1:
                retry_guidance = self._build_retry_prompt_for_stage(stage_name, parse_error="", validation_errors=validation_errors)
                continue
            self._record_stage_error(
                stage_name=stage_name,
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                raw_output=execution.raw_payload,
                validation_error=validation_error_text,
                retry_count=1,
            )
            return PlannerStageResult(success=False, errors=last_errors, raw_response=execution.raw_payload)

        return PlannerStageResult(success=False, errors=last_errors, raw_response=last_raw_response)

    def _parse_base_plan_payload(self, payload: Dict[str, Any]) -> BasePlan:
        return BasePlan.model_validate(payload)

    def _parse_internal_final_plan_payload(self, payload: Dict[str, Any]) -> InternalFinalPlan:
        data = dict(payload)
        if isinstance(data.get("raw_plan"), str):
            data["raw_plan"] = {"raw": data["raw_plan"]}
        if "raw_plan" not in data:
            data["raw_plan"] = payload
        return InternalFinalPlan.model_validate(data)

    def _validate_stage1_base_plan(self, base_plan: BasePlan, base_input: BasePlanInput) -> list[str]:
        errors: list[str] = []
        if not base_plan.allowed_node_types:
            errors.append("allowed_node_types must not be empty")
        unknown_types = [item.value for item in base_plan.allowed_node_types if item not in SUPPORTED_NODE_TYPES]
        if unknown_types:
            errors.append(f"allowed_node_types contains unsupported values: {unknown_types}")

        valid_context_ids = {item.resource_id for item in base_input.candidate_contexts}
        valid_bo_ids = {item.bo_id for item in base_input.candidate_bos}
        valid_function_ids = {item.resource_id for item in base_input.candidate_functions}

        unknown_contexts = [item for item in base_plan.required_resources.context_refs if item not in valid_context_ids]
        if unknown_contexts:
            errors.append(f"required_resources.context_refs contains unknown refs: {unknown_contexts}")

        unknown_bos = [item.bo_id for item in base_plan.required_resources.bo_refs if item.bo_id not in valid_bo_ids]
        if unknown_bos:
            errors.append(f"required_resources.bo_refs contains unknown refs: {unknown_bos}")

        unknown_functions = [item for item in base_plan.required_resources.function_refs if item not in valid_function_ids]
        if unknown_functions:
            errors.append(f"required_resources.function_refs contains unknown refs: {unknown_functions}")

        if not base_plan.plan_shape.needs_query:
            if AllowedNodeType.QUERY_CALL in base_plan.allowed_node_types:
                errors.append("needs_query=false but query_call is still allowed")
            if base_plan.plan_shape.preferred_query_kinds:
                errors.append("needs_query=false but preferred_query_kinds is not empty")
            if base_plan.return_shape == ReturnShape.QUERY_RESULT:
                errors.append("needs_query=false but return_shape=query_result")

        if base_plan.plan_shape.needs_query and not base_plan.required_resources.bo_refs:
            errors.append("needs_query=true but no bo_refs were selected")

        if not base_plan.plan_shape.needs_definitions and base_plan.definition_hints:
            errors.append("needs_definitions=false but definition_hints is not empty")

        if base_plan.plan_shape.needs_function_call:
            if AllowedNodeType.FUNCTION_CALL not in base_plan.allowed_node_types:
                errors.append("needs_function_call=true but function_call is missing from allowed_node_types")
            if not base_plan.required_resources.function_refs:
                errors.append("needs_function_call=true but no function_refs were selected")
        elif AllowedNodeType.FUNCTION_CALL in base_plan.allowed_node_types:
            errors.append("needs_function_call=false but function_call is still allowed")

        advanced_types = {
            AllowedNodeType.QUERY_CALL,
            AllowedNodeType.IF,
            AllowedNodeType.LIST_LITERAL,
            AllowedNodeType.INDEX_ACCESS,
        }
        if base_plan.plan_shape.estimated_complexity == ComplexityLevel.LOW and (
            any(item in advanced_types for item in base_plan.allowed_node_types) or len(base_plan.allowed_node_types) > 4
        ):
            errors.append("estimated_complexity=low conflicts with the selected node types")

        return errors

    def _validate_stage2_filtered_spec(self, spec: FilteredPlanSpec, base_plan: BasePlan) -> list[str]:
        errors: list[str] = []
        base_types = set(base_plan.allowed_node_types)
        widened_types = [item.value for item in spec.allowed_node_types if item not in base_types]
        if widened_types:
            errors.append(f"filtered spec widened allowed_node_types: {widened_types}")

        if not spec.allow_definitions and spec.max_definitions != 0:
            errors.append("allow_definitions=false requires max_definitions=0")
        if not spec.allow_definitions and spec.allowed_definition_kinds:
            errors.append("allow_definitions=false requires allowed_definition_kinds to be empty")

        if AllowedNodeType.QUERY_CALL not in spec.allowed_node_types:
            if spec.allowed_query_kinds:
                errors.append("query_call is disabled but allowed_query_kinds is not empty")
            if self._skeleton_contains_node_type(spec.example_output_skeleton, AllowedNodeType.QUERY_CALL.value):
                errors.append("query_call is disabled but still appears in example_output_skeleton")

        if base_plan.plan_shape.needs_query and not spec.allowed_query_kinds:
            errors.append("base plan requires query but filtered spec removed all query kinds")

        if not set(spec.allowed_return_shapes).issubset({base_plan.return_shape} if base_plan.return_shape != ReturnShape.UNKNOWN else set(spec.allowed_return_shapes)):
            errors.append("allowed_return_shapes is wider than the base plan return_shape")

        if not set(item.field_path for item in spec.field_constraints):
            errors.append("field_constraints must not be empty")

        return errors

    def _validate_stage3_final_plan(
        self,
        final_plan: InternalFinalPlan,
        spec: FilteredPlanSpec,
        base_plan: BasePlan,
        final_input: FinalPlanInput | None = None,
    ) -> list[str]:
        errors: list[str] = []
        if not spec.allow_definitions and final_plan.definitions:
            errors.append("definitions are disabled by filtered spec")
        if len(final_plan.definitions) > spec.max_definitions:
            errors.append(f"definitions exceeds filtered limit {spec.max_definitions}")

        allowed_node_types = set(spec.allowed_node_types)
        seen_node_types: list[AllowedNodeType] = []
        for definition in final_plan.definitions:
            seen_node_types.extend(_collect_node_types(definition.expr))
        seen_node_types.extend(_collect_node_types(final_plan.return_expr))
        disallowed_types = [item.value for item in seen_node_types if item not in allowed_node_types]
        if disallowed_types:
            errors.append(f"final plan uses disallowed node types: {sorted(set(disallowed_types))}")

        query_kinds = [
            query.query_kind
            for definition in final_plan.definitions
            for query in collect_query_refs(definition.expr)
        ] + [query.query_kind for query in collect_query_refs(final_plan.return_expr)]
        invalid_query_kinds = [item for item in query_kinds if item not in {kind.value for kind in spec.allowed_query_kinds}]
        if invalid_query_kinds:
            errors.append(f"final plan uses disallowed query kinds: {sorted(set(invalid_query_kinds))}")

        if spec.allowed_binary_operators:
            invalid_binary_ops = [
                node.operator
                for definition in final_plan.definitions
                for node in self._collect_binary_nodes(definition.expr)
                if node.operator not in spec.allowed_binary_operators
            ]
            invalid_binary_ops.extend(
                node.operator for node in self._collect_binary_nodes(final_plan.return_expr) if node.operator not in spec.allowed_binary_operators
            )
            if invalid_binary_ops:
                errors.append(f"final plan uses disallowed binary operators: {sorted(set(invalid_binary_ops))}")

        if spec.allowed_unary_operators:
            invalid_unary_ops = [
                node.operator
                for definition in final_plan.definitions
                for node in self._collect_unary_nodes(definition.expr)
                if node.operator not in spec.allowed_unary_operators
            ]
            invalid_unary_ops.extend(
                node.operator for node in self._collect_unary_nodes(final_plan.return_expr) if node.operator not in spec.allowed_unary_operators
            )
            if invalid_unary_ops:
                errors.append(f"final plan uses disallowed unary operators: {sorted(set(invalid_unary_ops))}")

        return_shape = _infer_return_shape(final_plan.return_expr)
        if return_shape not in spec.allowed_return_shapes:
            errors.append(f"return_expr shape {return_shape.value} is not allowed")

        limits = ProgramPlanLimits(
            max_definitions=spec.max_definitions,
            max_expr_depth_per_definition=spec.max_expr_depth_per_definition or 1,
            max_return_expr_depth=spec.max_return_expr_depth,
            max_total_expr_nodes=spec.max_total_expr_nodes,
            max_if_nodes_total=max(1, spec.max_total_expr_nodes),
        )
        structure_issues = validate_program_plan_structure(self._adapt_internal_final_plan_to_program_plan(final_plan), limits)
        errors.extend(f"{item.code}: {item.message}" for item in structure_issues)

        if final_input is not None:
            allowed_context_paths = {
                alias
                for item in final_input.filtered_resources.context_refs
                for alias in _context_ref_aliases(item.ref)
            }
            allowed_bo_ids = {item.bo_id for item in final_input.filtered_resources.bo_refs}
            allowed_function_ids = {item.resource_id for item in final_input.filtered_resources.function_refs}
            for context_path in [
                item
                for definition in final_plan.definitions
                for item in (collect_context_refs(definition.expr) + collect_local_refs(definition.expr))
            ] + (collect_context_refs(final_plan.return_expr) + collect_local_refs(final_plan.return_expr)):
                if context_path not in allowed_context_paths:
                    errors.append(f"context/local ref not allowed by filtered resources: {context_path}")
            for query in [
                query
                for definition in final_plan.definitions
                for query in collect_query_refs(definition.expr)
            ] + collect_query_refs(final_plan.return_expr):
                if query.bo_id and query.bo_id not in allowed_bo_ids:
                    errors.append(f"query bo_id not allowed by filtered resources: {query.bo_id}")
            for function in [
                function
                for definition in final_plan.definitions
                for function in collect_function_refs(definition.expr)
            ] + collect_function_refs(final_plan.return_expr):
                function_key = function.function_id or function.function_name or ""
                if function_key and function_key not in allowed_function_ids:
                    errors.append(f"function call not allowed by filtered resources: {function_key}")

        duplicate_names = [name for name in _sorted_unique([item.name for item in final_plan.definitions]) if [item.name for item in final_plan.definitions].count(name) > 1]
        if duplicate_names:
            errors.append(f"duplicate definition names are not allowed: {duplicate_names}")

        return errors

    def _build_retry_prompt_for_stage(self, stage_name: str, *, parse_error: str, validation_errors: list[str]) -> str:
        error_lines = []
        if parse_error:
            error_lines.append(f"Parse error: {parse_error}")
        if validation_errors:
            error_lines.append("Validation errors:")
            error_lines.extend(f"- {item}" for item in validation_errors)
        guidance = "\n".join(error_lines).strip()
        if not guidance:
            return ""
        return (
            f"Retry for stage {stage_name}. Fix the response so it matches the schema exactly and resolves these issues.\n"
            f"{guidance}"
        )

    def _collect_planner_diagnostics(self) -> list[PlanDiagnostic]:
        diagnostics: list[PlanDiagnostic] = []
        for item in self.planner_diagnostics.stage_errors:
            if item.parse_error:
                diagnostics.append(
                    PlanDiagnostic(
                        code=f"{item.stage_name}_parse_failed",
                        message=item.parse_error,
                        path=item.stage_name,
                        severity="error",
                    )
                )
            if item.validation_error:
                diagnostics.append(
                    PlanDiagnostic(
                        code=f"{item.stage_name}_validation_failed",
                        message=item.validation_error,
                        path=item.stage_name,
                        severity="error",
                    )
                )
        if not diagnostics and self.planner_diagnostics.stage_trace:
            diagnostics.append(
                PlanDiagnostic(
                    code="planner_failed",
                    message="llm planner failed without a structured stage error",
                    path="planner",
                    severity="error",
                )
            )
        return diagnostics

    def _record_stage_error(
        self,
        *,
        stage_name: str,
        prompt_key: str,
        prompt_version: str,
        raw_output: dict[str, Any] | None,
        parse_error: str = "",
        validation_error: str = "",
        retry_count: int = 0,
    ) -> None:
        self.planner_diagnostics.stage_errors.append(
            StageError(
                stage_name=stage_name,
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                raw_output=raw_output,
                parse_error=parse_error,
                validation_error=validation_error,
                retry_count=retry_count,
            )
        )

    def _build_stage1_prompt_params(self, base_input: BasePlanInput, retry_guidance: str) -> dict[str, Any]:
        planner_context = {
            "user_query": base_input.user_query,
            "node": base_input.node_info.model_dump(mode="python"),
            "resource_summary": {
                "context_count": len(base_input.candidate_contexts),
                "bo_count": len(base_input.candidate_bos),
                "function_count": len(base_input.candidate_functions),
            },
        }
        schema_summary = {
            "required_fields": [
                "goal",
                "required_resources",
                "plan_shape",
                "allowed_node_types",
                "return_shape",
                "definition_hints",
            ],
            "required_resources": {
                "context_refs": "list[str], must use candidate_contexts.resource_id",
                "bo_refs": "list[BOSelectionTerm], must reuse candidate_bos entries",
                "function_refs": "list[str], must use candidate_functions.resource_id",
            },
            "plan_shape": {
                "needs_definitions": "bool",
                "needs_query": "bool",
                "needs_condition": "bool",
                "needs_function_call": "bool",
                "estimated_complexity": [item.value for item in ComplexityLevel],
                "preferred_query_kinds": [item.value for item in AllowedQueryKind],
            },
            "allowed_node_types": [item.value for item in SUPPORTED_NODE_TYPES],
            "return_shape": [item.value for item in ReturnShape],
        }
        few_shot = [
            {
                "input": {
                    "user_query": "return customer gender directly",
                    "node_info": {"node_name": "title"},
                },
                "output": {
                    "goal": "read an existing context field and return it",
                    "required_resources": {
                        "context_refs": ["context:$ctx$.customer.gender"],
                        "bo_refs": [],
                        "function_refs": [],
                    },
                    "plan_shape": {
                        "needs_definitions": False,
                        "needs_query": False,
                        "needs_condition": False,
                        "needs_function_call": False,
                        "estimated_complexity": "low",
                        "preferred_query_kinds": [],
                    },
                    "allowed_node_types": ["context_ref"],
                    "return_shape": "direct_ref",
                    "definition_hints": [],
                    "validation_notes": [],
                    "raw_reasoning_summary": "direct reference only",
                },
            },
            {
                "input": {
                    "user_query": "query customer gender and derive title",
                    "node_info": {"node_name": "title"},
                },
                "output": {
                    "goal": "query customer data then compute a title",
                    "required_resources": {
                        "context_refs": ["context:$ctx$.customer.id"],
                        "bo_refs": [
                            {
                                "bo_id": "bo:CustomerBO",
                                "bo_name": "CustomerBO",
                                "field_ids": ["bo:CustomerBO:field:gender"],
                                "naming_sql_ids": ["bo:CustomerBO:sql:findById"],
                                "data_source": "crm",
                                "available_query_kinds": ["select_one"],
                            }
                        ],
                        "function_refs": [],
                    },
                    "plan_shape": {
                        "needs_definitions": True,
                        "needs_query": True,
                        "needs_condition": True,
                        "needs_function_call": False,
                        "estimated_complexity": "medium",
                        "preferred_query_kinds": ["select_one"],
                    },
                    "allowed_node_types": ["context_ref", "query_call", "if", "binary_op", "literal", "var_ref"],
                    "return_shape": "conditional_result",
                    "definition_hints": [{"name": "customer_gender", "purpose": "cache the queried gender"}],
                    "validation_notes": [],
                    "raw_reasoning_summary": "use one query and one conditional",
                },
            },
        ]
        payload = base_input.model_dump(mode="python")
        return {
            "base_plan_input_json": json.dumps(payload, ensure_ascii=False),
            "base_plan_schema_json": json.dumps(schema_summary, ensure_ascii=False),
            "base_plan_examples_json": json.dumps(few_shot, ensure_ascii=False),
            "planner_context_json": json.dumps(planner_context, ensure_ascii=False),
            "retry_guidance": retry_guidance or "None",
            "base_plan_input": payload,
            "base_plan_schema": schema_summary,
            "base_plan_examples": few_shot,
            "planner_context": planner_context,
        }

    def _build_stage3_prompt_params(self, final_input: FinalPlanInput, retry_guidance: str) -> dict[str, Any]:
        schema_summary = {
            "required_fields": ["definitions", "return_expr"],
            "definitions": {
                "required": final_input.filtered_spec.allow_definitions,
                "kind": [item.value for item in final_input.filtered_spec.allowed_definition_kinds],
                "max_items": final_input.filtered_spec.max_definitions,
            },
            "return_expr": {
                "allowed_node_types": [item.value for item in final_input.filtered_spec.allowed_node_types],
                "allowed_return_shapes": [item.value for item in final_input.filtered_spec.allowed_return_shapes],
            },
            "node_shapes": {
                "context_ref": {
                    "required_fields": ["type", "path"],
                    "example": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                    "forbidden_fields": ["resource_id", "ref", "label", "description", "category"],
                },
                "local_ref": {
                    "required_fields": ["type", "path"],
                    "example": {"type": "local_ref", "path": "$local$.invoiceId"},
                    "forbidden_fields": ["resource_id", "ref", "label", "description", "category"],
                },
                "function_call": {
                    "required_fields": ["type", "function_id", "args"],
                    "example": {"type": "function_call", "function_id": "function:Customer.GetSalutation", "args": []},
                },
            },
            "query_call": {
                "allowed_query_kinds": [item.value for item in final_input.filtered_spec.allowed_query_kinds],
            },
        }
        filtered_resources = self._build_stage3_filtered_resources_view(final_input)
        environment_payload = self._build_stage3_environment_payload(final_input)
        base_plan_summary = final_input.base_plan.model_dump(mode="python")
        filtered_spec_payload = final_input.filtered_spec.model_dump(mode="python")
        return {
            "user_query": final_input.user_query,
            "user_requirement": final_input.user_query,
            "node_def_json": json.dumps(final_input.node_info.model_dump(mode="python"), ensure_ascii=False),
            "base_plan_json": json.dumps(base_plan_summary, ensure_ascii=False),
            "filtered_spec_json": json.dumps(filtered_spec_payload, ensure_ascii=False),
            "filtered_resources_json": json.dumps(filtered_resources, ensure_ascii=False),
            "final_plan_schema_json": json.dumps(schema_summary, ensure_ascii=False),
            "final_plan_skeleton_json": json.dumps(final_input.filtered_spec.example_output_skeleton, ensure_ascii=False),
            "environment_json": json.dumps(environment_payload, ensure_ascii=False),
            "retry_guidance": retry_guidance or "None",
            "node_def": final_input.node_info.model_dump(mode="python"),
            "base_plan": base_plan_summary,
            "filtered_spec": filtered_spec_payload,
            "filtered_resources": filtered_resources,
            "final_plan_schema": schema_summary,
            "final_plan_skeleton": final_input.filtered_spec.example_output_skeleton,
            "environment": environment_payload,
        }

    def _build_stage3_filtered_resources_view(self, final_input: FinalPlanInput) -> dict[str, Any]:
        return {
            "context_paths": [
                {
                    "path": item.ref,
                    "label": item.label,
                    "category": item.category,
                    "usage": "use this exact string in context_ref.path or local_ref.path",
                }
                for item in final_input.filtered_resources.context_refs
            ],
            "allowed_context_paths": [item.ref for item in final_input.filtered_resources.context_refs],
            "bos": [
                {
                    "bo_id": item.bo_id,
                    "bo_name": item.bo_name,
                    "field_ids": list(item.field_ids),
                    "naming_sql_ids": list(item.naming_sql_ids),
                    "data_source": item.data_source,
                    "available_query_kinds": [kind.value for kind in item.available_query_kinds],
                }
                for item in final_input.filtered_resources.bo_refs
            ],
            "functions": [
                {
                    "function_id": item.resource_id,
                    "display_name": item.label,
                    "usage": "use this exact string in function_call.function_id",
                }
                for item in final_input.filtered_resources.function_refs
            ],
        }

    def _build_field_constraints(
        self,
        *,
        allowed_node_types: list[AllowedNodeType],
        allowed_query_kinds: list[AllowedQueryKind],
        allow_definitions: bool,
        max_definitions: int,
        allowed_return_shapes: list[ReturnShape],
        allowed_binary_operators: list[str],
        allowed_unary_operators: list[str],
    ) -> list[FieldConstraintTerm]:
        constraints = [
            FieldConstraintTerm(
                field_path="definitions",
                required=allow_definitions,
                description="definitions may be omitted when allow_definitions is false",
                max_items=max_definitions,
            ),
            FieldConstraintTerm(
                field_path="return_expr.type",
                required=True,
                description="return_expr must use an allowed node type",
                allowed_values=[item.value for item in allowed_node_types],
            ),
            FieldConstraintTerm(
                field_path="return_shape",
                required=True,
                description="return_expr must match one of the allowed return shapes",
                allowed_values=[item.value for item in allowed_return_shapes],
            ),
        ]
        if allow_definitions:
            constraints.append(
                FieldConstraintTerm(
                    field_path="definitions[].kind",
                    required=True,
                    description="only variable definitions are supported",
                    allowed_values=["variable"],
                )
            )
        if allowed_query_kinds:
            constraints.append(
                FieldConstraintTerm(
                    field_path="query_call.query_kind",
                    required=True,
                    description="query_call must use the filtered query kinds",
                    allowed_values=[item.value for item in allowed_query_kinds],
                )
            )
        if allowed_binary_operators:
            constraints.append(
                FieldConstraintTerm(
                    field_path="binary_op.operator",
                    required=True,
                    description="binary operators are filtered by stage2",
                    allowed_values=allowed_binary_operators,
                )
            )
        if allowed_unary_operators:
            constraints.append(
                FieldConstraintTerm(
                    field_path="unary_op.operator",
                    required=True,
                    description="unary operators are filtered by stage2",
                    allowed_values=allowed_unary_operators,
                )
            )
        return constraints

    def _build_final_plan_skeleton(
        self,
        *,
        base_plan: BasePlan,
        allowed_node_types: list[AllowedNodeType],
        allow_definitions: bool,
    ) -> dict[str, Any]:
        return_expr = self._default_expr_skeleton(base_plan.return_shape, allowed_node_types, base_plan)
        payload: dict[str, Any] = {"definitions": [], "return_expr": return_expr}
        if allow_definitions and base_plan.definition_hints:
            payload["definitions"] = [
                {
                    "kind": "variable",
                    "name": item.name,
                    "expr": self._default_expr_skeleton(ReturnShape.DIRECT_REF, allowed_node_types, base_plan),
                }
                for item in base_plan.definition_hints[:1]
            ]
            if AllowedNodeType.VAR_REF in allowed_node_types:
                payload["return_expr"] = {"type": "var_ref", "name": base_plan.definition_hints[0].name}
        return payload

    def _default_expr_skeleton(
        self,
        return_shape: ReturnShape,
        allowed_node_types: list[AllowedNodeType],
        base_plan: BasePlan,
    ) -> dict[str, Any]:
        if return_shape == ReturnShape.QUERY_RESULT and AllowedNodeType.QUERY_CALL in allowed_node_types and base_plan.required_resources.bo_refs:
            bo = base_plan.required_resources.bo_refs[0]
            query_kind = (
                base_plan.plan_shape.preferred_query_kinds[0].value
                if base_plan.plan_shape.preferred_query_kinds
                else AllowedQueryKind.SELECT_ONE.value
            )
            return {
                "type": "query_call",
                "query_kind": query_kind,
                "source_name": bo.bo_name,
                "bo_id": bo.bo_id,
                "field": bo.field_ids[0].split(":")[-1] if bo.field_ids else None,
                "data_source": bo.data_source or None,
                "naming_sql_id": bo.naming_sql_ids[0] if bo.naming_sql_ids else None,
                "filters": [],
                "pairs": [],
            }
        if return_shape == ReturnShape.FUNCTION_RESULT and AllowedNodeType.FUNCTION_CALL in allowed_node_types and base_plan.required_resources.function_refs:
            return {
                "type": "function_call",
                "function_id": base_plan.required_resources.function_refs[0],
                "args": [],
            }
        if return_shape == ReturnShape.CONDITIONAL_RESULT and AllowedNodeType.IF in allowed_node_types:
            return {
                "type": "if",
                "condition": {"type": "literal", "value": True},
                "then_expr": {"type": "literal", "value": None},
                "else_expr": {"type": "literal", "value": None},
            }
        if return_shape == ReturnShape.LIST_RESULT and AllowedNodeType.LIST_LITERAL in allowed_node_types:
            return {"type": "list_literal", "items": []}
        if return_shape == ReturnShape.OBJECT_FIELD and AllowedNodeType.FIELD_ACCESS in allowed_node_types:
            return {
                "type": "field_access",
                "base": {"type": "context_ref", "path": "<context-path>"},
                "field": "<field>",
            }
        if AllowedNodeType.CONTEXT_REF in allowed_node_types and base_plan.required_resources.context_refs:
            return {"type": "context_ref", "path": "<allowed-context-path>"}
        return {"type": "literal", "value": None}

    def _build_stage3_environment_payload(self, final_input: FinalPlanInput) -> dict[str, Any]:
        global_contexts = [item for item in final_input.filtered_resources.context_refs if item.category == "global_context"]
        local_contexts = [item for item in final_input.filtered_resources.context_refs if item.category == "local_context"]
        return {
            "selected_global_context_ids": [item.resource_id for item in global_contexts],
            "selected_local_context_ids": [item.resource_id for item in local_contexts],
            "selected_bo_ids": [item.bo_id for item in final_input.filtered_resources.bo_refs],
            "selected_function_ids": [item.resource_id for item in final_input.filtered_resources.function_refs],
            "selected_global_contexts": [
                {
                    "resource_id": item.resource_id,
                    "path": item.ref,
                    "name": item.label,
                    "description": item.description,
                }
                for item in global_contexts
            ],
            "selected_local_context_nodes": [
                {
                    "resource_id": item.resource_id,
                    "access_path": item.ref,
                    "property_name": item.label,
                    "annotation": item.description,
                }
                for item in local_contexts
            ],
            "selected_bos": [item.model_dump(mode="python") for item in final_input.filtered_resources.bo_refs],
            "selected_functions": [
                {
                    "resource_id": item.resource_id,
                    "function_id": item.ref,
                    "full_name": item.label,
                    "description": item.description,
                }
                for item in final_input.filtered_resources.function_refs
            ],
        }


    def _shrink_query_kinds(self, base_plan: BasePlan) -> list[AllowedQueryKind]:
        if not base_plan.required_resources.bo_refs:
            return []
        preferred = [item for item in base_plan.plan_shape.preferred_query_kinds if item in SUPPORTED_QUERY_KINDS]
        if preferred:
            return preferred[:1] if len(preferred) == 1 else preferred
        union: list[AllowedQueryKind] = []
        for bo in base_plan.required_resources.bo_refs:
            union.extend(bo.available_query_kinds)
        union = _sorted_allowed_query_kinds(union)
        if base_plan.return_shape == ReturnShape.LIST_RESULT:
            plural = [item for item in union if item in {AllowedQueryKind.SELECT, AllowedQueryKind.FETCH}]
            return plural or union
        singular = [item for item in union if item in {AllowedQueryKind.SELECT_ONE, AllowedQueryKind.FETCH_ONE}]
        return singular[:1] if len(singular) == 1 else (singular or union)

    def _available_query_kinds_for_bo(self, field_ids: list[str], naming_sql_ids: list[str]) -> list[AllowedQueryKind]:
        kinds: list[AllowedQueryKind] = []
        if field_ids:
            kinds.extend([AllowedQueryKind.SELECT_ONE, AllowedQueryKind.SELECT])
        if naming_sql_ids:
            kinds.extend([AllowedQueryKind.FETCH_ONE, AllowedQueryKind.FETCH])
        return _sorted_allowed_query_kinds(kinds)

    def _build_env_payload(self, env: FilteredEnvironment) -> Dict[str, Any]:
        return {
            "selected_global_context_ids": list(env.selected_global_context_ids),
            "selected_local_context_ids": list(env.selected_local_context_ids),
            "selected_bo_ids": list(env.selected_bo_ids),
            "selected_function_ids": list(env.selected_function_ids),
            "selected_global_contexts": [
                {
                    "resource_id": item.resource_id,
                    "path": item.path,
                    "name": item.name,
                    "description": item.description,
                    "scope": item.scope,
                }
                for item in env.selected_global_contexts
            ],
            "selected_local_context_nodes": [
                {
                    "resource_id": item.resource_id,
                    "property_id": item.property_id,
                    "property_name": item.property_name,
                    "access_path": item.access_path,
                    "annotation": item.annotation,
                }
                for item in env.visible_local_context.ordered_nodes
            ],
            "selected_bos": [
                {
                    "resource_id": item.resource_id,
                    "bo_name": item.bo_name,
                    "description": item.description,
                    "data_source": item.data_source,
                    "fields": [
                        {
                            "field_id": field_id,
                            "name": field_id.split(":")[-1],
                        }
                        for field_id in item.field_ids
                    ],
                    "naming_sqls": [
                        {
                            "naming_sql_id": sql_id,
                            "name": item.naming_sql_name_by_key.get(sql_id) or sql_id.split(":")[-1],
                            "param_names": list(item.naming_sql_param_names_by_key.get(sql_id) or []),
                        }
                        for sql_id in item.naming_sql_ids
                    ],
                }
                for item in env.selected_bos
            ],
            "selected_functions": [
                {
                    "resource_id": item.resource_id,
                    "function_id": item.function_id,
                    "full_name": item.full_name,
                    "description": item.description,
                    "params": [
                        {
                            "param_name": param.param_name,
                            "normalized_param_type": param.normalized_param_type,
                        }
                        for param in item.param_defs
                    ],
                    "return_type": item.return_type,
                }
                for item in env.selected_functions
            ],
        }

    def _failed_plan(
        self,
        raw_plan: Dict[str, Any] | None,
        default_code: str,
        errors: list[LLMErrorRecord],
    ) -> ProgramPlan:
        diagnostics = self._collect_planner_diagnostics()
        diagnostics.extend(
            [
                PlanDiagnostic(
                    code=item.code or default_code,
                    message=item.message,
                    path=item.stage or "raw_plan",
                    severity="error",
                )
                for item in errors
            ]
        )
        if not diagnostics:
            diagnostics = [
                PlanDiagnostic(
                    code=default_code,
                    message="llm planner returned an invalid response",
                    path="raw_plan",
                    severity="error",
                )
            ]
        elif all(item.code != default_code for item in diagnostics):
            diagnostics.append(
                PlanDiagnostic(
                    code=default_code,
                    message="llm planner returned an invalid response",
                    path="raw_plan",
                    severity="error",
                )
            )
        return ProgramPlan(
            definitions=[],
            return_expr=LiteralPlanNode(type="literal", value=None),
            raw_plan=raw_plan or {"planner_diagnostics": self.planner_diagnostics.model_dump(mode="python")},
            diagnostics=diagnostics,
        )

    def _make_llm_error(
        self,
        stage: str,
        code: str,
        message: str,
        raw_payload: dict[str, Any] | None,
    ) -> LLMErrorRecord:
        return LLMErrorRecord(stage=stage, code=code, message=message, raw_payload=raw_payload)

    def _collect_binary_nodes(self, expr: ExprPlanNode) -> list[BinaryOpPlanNode]:
        nodes: list[BinaryOpPlanNode] = [expr] if isinstance(expr, BinaryOpPlanNode) else []
        for child in _child_expressions(expr):
            nodes.extend(self._collect_binary_nodes(child))
        return nodes

    def _collect_unary_nodes(self, expr: ExprPlanNode) -> list[UnaryOpPlanNode]:
        nodes: list[UnaryOpPlanNode] = [expr] if isinstance(expr, UnaryOpPlanNode) else []
        for child in _child_expressions(expr):
            nodes.extend(self._collect_unary_nodes(child))
        return nodes

    def _skeleton_contains_node_type(self, payload: Any, node_type: str) -> bool:
        if isinstance(payload, dict):
            if payload.get("type") == node_type:
                return True
            return any(self._skeleton_contains_node_type(value, node_type) for value in payload.values())
        if isinstance(payload, list):
            return any(self._skeleton_contains_node_type(item, node_type) for item in payload)
        return False
