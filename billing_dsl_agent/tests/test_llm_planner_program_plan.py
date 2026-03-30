from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.llm_planner_models import AllowedNodeType, AllowedQueryKind, BasePlan
from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    FilteredEnvironment,
    FunctionResource,
    LLMAttemptRecord,
    LLMErrorRecord,
    NodeDef,
    NormalizedLocalContextNode,
    ProgramPlan,
    ResourceRegistry,
    ValidationIssue,
    VisibleLocalContextSet,
)
from billing_dsl_agent.services.llm_client import StructuredExecutionResult


def _env() -> FilteredEnvironment:
    return FilteredEnvironment(
        registry=ResourceRegistry(),
        selected_global_context_ids=["context:$ctx$.customer.gender", "context:$ctx$.customer.id"],
        selected_local_context_ids=["local_context:lc_invoice_id"],
        selected_bo_ids=["bo:CustomerBO"],
        selected_function_ids=["function:Customer.GetSalutation"],
        selected_global_contexts=[
            ContextResource(
                resource_id="context:$ctx$.customer.gender",
                name="gender",
                path="$ctx$.customer.gender",
            ),
            ContextResource(
                resource_id="context:$ctx$.customer.id",
                name="id",
                path="$ctx$.customer.id",
            ),
        ],
        visible_local_context=VisibleLocalContextSet(
            nodes_by_id={
                "local_context:lc_invoice_id": NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            },
            nodes_by_property_name={
                "invoiceId": NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            },
            ordered_nodes=[
                NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            ],
        ),
        selected_bos=[
            BOResource(
                resource_id="bo:CustomerBO",
                bo_name="CustomerBO",
                field_ids=["bo:CustomerBO:field:gender", "bo:CustomerBO:field:id"],
                naming_sql_ids=["bo:CustomerBO:sql:findById"],
                data_source="crm",
            )
        ],
        selected_functions=[
            FunctionResource(
                resource_id="function:Customer.GetSalutation",
                function_id="function:Customer.GetSalutation",
                name="GetSalutation",
                full_name="Customer.GetSalutation",
            )
        ],
    )


def _node() -> NodeDef:
    return NodeDef(node_id="n1", node_path="invoice.customer.title", node_name="title")


def _base_plan_response(*, needs_definitions: bool = True, needs_query: bool = False) -> dict[str, Any]:
    return {
        "goal": "derive title",
        "required_resources": {
            "context_refs": ["context:$ctx$.customer.gender"] if not needs_query else ["context:$ctx$.customer.id"],
            "bo_refs": [
                {
                    "bo_id": "bo:CustomerBO",
                    "bo_name": "CustomerBO",
                    "field_ids": ["bo:CustomerBO:field:gender"],
                    "naming_sql_ids": ["bo:CustomerBO:sql:findById"],
                    "data_source": "crm",
                    "available_query_kinds": ["select_one", "fetch_one"],
                }
            ]
            if needs_query
            else [],
            "function_refs": ["function:Customer.GetSalutation"] if not needs_query else [],
        },
        "plan_shape": {
            "needs_definitions": needs_definitions,
            "needs_query": needs_query,
            "needs_condition": not needs_query,
            "needs_function_call": not needs_query,
            "estimated_complexity": "medium",
            "preferred_query_kinds": ["select_one"] if needs_query else [],
        },
        "allowed_node_types": ["context_ref", "literal", "binary_op", "if", "function_call", "var_ref"]
        if not needs_query
        else ["context_ref", "query_call", "var_ref"],
        "return_shape": "function_result" if not needs_query else "query_result",
        "definition_hints": [{"name": "customer_gender", "purpose": "cache gender"}] if needs_definitions else [],
        "validation_notes": [],
        "raw_reasoning_summary": "structured base plan",
    }


def _final_plan_response() -> dict[str, Any]:
    return {
        "definitions": [
            {
                "kind": "variable",
                "name": "customer_gender",
                "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
            }
        ],
        "return_expr": {
            "type": "function_call",
            "function_id": "function:Customer.GetSalutation",
            "args": [{"type": "var_ref", "name": "customer_gender"}],
        },
    }


@dataclass(slots=True)
class SequencedStubClient:
    responses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    last_payload: dict[str, Any] | None = None
    counters: dict[str, int] = field(default_factory=dict)

    def execute_structured(
        self,
        *,
        prompt_key: str,
        lang: str,
        prompt_params: dict[str, Any] | None,
        response_model: Any,
        stage: str,
        attempt_index: int = 1,
        response_parser: Any = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[Any]:
        self.last_payload = dict(prompt_params or {})
        stage_counter = self.counters.get(stage, 0)
        self.counters[stage] = stage_counter + 1
        payloads = self.responses.get(stage) or []
        raw_response = payloads[min(stage_counter, len(payloads) - 1)] if payloads else None
        parsed = None
        errors: list[LLMErrorRecord] = []
        if raw_response is not None:
            try:
                if response_parser is not None:
                    parsed = response_parser(raw_response)
                elif response_model is not None:
                    parsed = response_model.model_validate(raw_response)
            except Exception as exc:
                errors.append(
                    LLMErrorRecord(
                        stage=stage,
                        code="response_schema_error",
                        message=str(exc),
                        raw_payload=raw_response,
                        exception_type=type(exc).__name__,
                    )
                )
        return StructuredExecutionResult(
            parsed=parsed,
            errors=errors,
            raw_payload=raw_response,
            attempt=LLMAttemptRecord(
                stage=stage,
                attempt_index=attempt_index,
                request_payload=self.last_payload,
                response_payload=raw_response,
                parsed_ok=parsed is not None and not errors,
                errors=errors,
            ),
        )


def test_stage1_success_generates_base_plan() -> None:
    planner = LLMPlanner(StubOpenAIClient(stage_responses={"plan_base": _base_plan_response()}))
    result = planner._run_stage1_base_plan(planner._build_base_plan_input("generate title", _node(), _env()))
    assert result.success is True
    assert result.payload is not None
    assert result.payload.plan_shape.needs_function_call is True
    assert result.payload.allowed_node_types[0] == AllowedNodeType.CONTEXT_REF


def test_stage1_output_illegal_node_type_is_blocked() -> None:
    planner = LLMPlanner(StubOpenAIClient(stage_responses={"plan_base": {**_base_plan_response(), "allowed_node_types": ["bad_node"]}}))
    plan = planner.plan("generate title", _node(), _env())
    assert any(item.code == "plan_base_parse_failed" for item in plan.diagnostics)


def test_stage2_builds_trimmed_spec_from_base_plan() -> None:
    planner = LLMPlanner(StubOpenAIClient())
    base_plan = BasePlan.model_validate(_base_plan_response())
    spec_result = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits))
    assert spec_result.success is True
    assert spec_result.payload is not None
    assert spec_result.payload.allow_definitions is True
    assert AllowedNodeType.FUNCTION_CALL in spec_result.payload.allowed_node_types


def test_stage2_removes_query_call_when_needs_query_false() -> None:
    planner = LLMPlanner(StubOpenAIClient())
    payload = _base_plan_response(needs_definitions=False, needs_query=False)
    payload["allowed_node_types"] = ["context_ref", "query_call", "literal"]
    base_plan = BasePlan.model_validate(payload)
    spec = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits)).payload
    assert spec is not None
    assert AllowedNodeType.QUERY_CALL not in spec.allowed_node_types
    assert spec.allowed_query_kinds == []


def test_stage2_disables_definitions_when_not_needed() -> None:
    planner = LLMPlanner(StubOpenAIClient())
    base_plan = BasePlan.model_validate(_base_plan_response(needs_definitions=False))
    spec = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits)).payload
    assert spec is not None
    assert spec.allow_definitions is False
    assert spec.max_definitions == 0


def test_stage3_only_uses_trimmed_nodes() -> None:
    base_plan = BasePlan.model_validate(_base_plan_response(needs_definitions=False))
    client = StubOpenAIClient(
        stage_responses={
            "plan_final": {
                "definitions": [],
                "return_expr": {
                    "type": "function_call",
                    "function_id": "function:Customer.GetSalutation",
                    "args": [],
                },
            },
        }
    )
    planner = LLMPlanner(client)
    spec = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits)).payload
    assert spec is not None
    spec.allowed_node_types = [AllowedNodeType.LITERAL]
    final_input = planner._build_final_plan_input(
        user_requirement="generate title",
        node_def=_node(),
        env=_env(),
        base_plan=base_plan,
        filtered_spec=spec,
        runtime_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits,
    )
    result = planner._run_stage3_final_plan(final_input)
    assert result.success is False
    assert any(item.code == "stage_validation_error" for item in result.errors)


def test_stage3_extra_fields_raise_error() -> None:
    planner = LLMPlanner(StubOpenAIClient(stage_responses={"plan_final": {"definitions": [], "return_expr": {"type": "literal", "value": "ok", "extra": True}}}))
    base_plan = BasePlan.model_validate(_base_plan_response(needs_definitions=False))
    spec = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits)).payload
    assert spec is not None
    final_input = planner._build_final_plan_input(
        user_requirement="generate title",
        node_def=_node(),
        env=_env(),
        base_plan=base_plan,
        filtered_spec=spec,
        runtime_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits,
    )
    result = planner._run_stage3_final_plan(final_input)
    assert result.success is False
    assert any(item.code == "response_schema_error" for item in result.errors)


def test_stage3_rejects_unallowed_query_kind() -> None:
    payload = _base_plan_response(needs_definitions=False, needs_query=True)
    base_plan = BasePlan.model_validate(payload)
    planner = LLMPlanner(
        StubOpenAIClient(
            stage_responses={
                "plan_final": {
                    "definitions": [],
                    "return_expr": {
                        "type": "query_call",
                        "query_kind": "fetch_one",
                        "source_name": "CustomerBO",
                        "bo_id": "bo:CustomerBO",
                        "naming_sql_id": "bo:CustomerBO:sql:findById",
                        "pairs": [{"key": "id", "value": {"type": "context_ref", "path": "$ctx$.customer.id"}}],
                    },
                },
            }
        )
    )
    spec = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits)).payload
    assert spec is not None
    spec.allowed_query_kinds = [AllowedQueryKind.SELECT_ONE]
    final_input = planner._build_final_plan_input(
        user_requirement="query title",
        node_def=_node(),
        env=_env(),
        base_plan=base_plan,
        filtered_spec=spec,
        runtime_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits,
    )
    result = planner._run_stage3_final_plan(final_input)
    assert result.success is False
    assert any("disallowed query kinds" in item.message for item in result.errors)


def test_stage1_retries_once_after_failure() -> None:
    client = SequencedStubClient(
        responses={
            "plan_base": [
                {"bad": "payload"},
                _base_plan_response(),
            ]
        }
    )
    planner = LLMPlanner(client)
    result = planner._run_stage1_base_plan(planner._build_base_plan_input("generate title", _node(), _env()))
    assert result.success is True
    assert len(planner.plan_attempts) == 2
    assert planner.plan_attempts[0].stage == "plan_base"


def test_stage3_retries_once_after_failure() -> None:
    client = SequencedStubClient(
        responses={
            "plan_final": [
                {"definitions": [], "return_expr": {"type": "literal", "value": "ok", "extra": True}},
                _final_plan_response(),
            ]
        }
    )
    planner = LLMPlanner(client)
    base_plan = BasePlan.model_validate(_base_plan_response())
    spec = planner._build_filtered_spec(planner._build_filtered_spec_input(base_plan=base_plan, planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits)).payload
    assert spec is not None
    final_input = planner._build_final_plan_input(
        user_requirement="generate title",
        node_def=_node(),
        env=_env(),
        base_plan=base_plan,
        filtered_spec=spec,
        runtime_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits,
    )
    result = planner._run_stage3_final_plan(final_input)
    assert result.success is True
    assert len(planner.plan_attempts) == 2
    assert planner.plan_attempts[-1].stage == "plan_final"


def test_external_plan_returns_program_plan_type_unchanged() -> None:
    planner = LLMPlanner(
        StubOpenAIClient(
            stage_responses={
                "plan_base": _base_plan_response(),
                "plan_final": _final_plan_response(),
            }
        )
    )
    plan = planner.plan("generate title", _node(), _env())
    assert isinstance(plan, ProgramPlan)
    assert plan.return_expr.type == "function_call"


def test_diagnostics_record_stage_failure_information() -> None:
    planner = LLMPlanner(StubOpenAIClient(stage_responses={"plan_base": {"bad": "payload"}}))
    plan = planner.plan("generate title", _node(), _env())
    assert planner.planner_diagnostics.stage_errors
    assert planner.planner_diagnostics.stage_errors[0].stage_name == "plan_base"
    assert any(item.code == "plan_base_parse_failed" for item in plan.diagnostics)


def test_planner_repair_payload_contains_structured_issues() -> None:
    client = StubOpenAIClient(
        stage_responses={
            "plan_base": _base_plan_response(needs_definitions=False),
            "plan_final": {"definitions": [], "return_expr": {"type": "literal", "value": "ok"}},
        },
        repair_response={"definitions": [], "return_expr": {"type": "literal", "value": "fixed"}},
    )
    planner = LLMPlanner(client)
    invalid_plan = planner.plan("generate title", _node(), _env())
    repaired = planner.repair(
        invalid_plan,
        _env(),
        [ValidationIssue(code="undefined_var_ref", message="missing variable", path="return_expr")],
    )
    assert repaired is not None
    assert client.last_payload is not None
    assert client.last_payload["issues"][0]["code"] == "undefined_var_ref"


def test_stage3_prompt_uses_context_paths_not_context_resource_ids() -> None:
    planner = LLMPlanner(StubOpenAIClient())
    base_plan = BasePlan.model_validate(_base_plan_response(needs_definitions=False))
    spec = planner._build_filtered_spec(
        planner._build_filtered_spec_input(
            base_plan=base_plan,
            planner_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits,
        )
    ).payload
    assert spec is not None
    final_input = planner._build_final_plan_input(
        user_requirement="generate title",
        node_def=_node(),
        env=_env(),
        base_plan=base_plan,
        filtered_spec=spec,
        runtime_limits=planner._build_base_plan_input("x", _node(), _env()).planner_runtime_limits,
    )
    prompt_params = planner._build_stage3_prompt_params(final_input, "")
    assert "allowed_context_paths" in prompt_params["filtered_resources"]
    assert prompt_params["filtered_resources"]["allowed_context_paths"][0] == "$ctx$.customer.gender"
    assert "resource_id" not in prompt_params["filtered_resources"]["context_paths"][0]
    assert "resource_id" in prompt_params["environment"]["selected_global_contexts"][0]
