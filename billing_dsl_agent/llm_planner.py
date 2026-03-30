from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from billing_dsl_agent.models import (
    FilteredEnvironment,
    LLMAttemptRecord,
    LLMErrorRecord,
    LiteralPlanNode,
    NodeDef,
    PlanDiagnostic,
    ProgramPlan,
    ValidationIssue,
)
from billing_dsl_agent.plan_validator import parse_program_plan_payload
from billing_dsl_agent.services.llm_client import OpenAILLMClient, StructuredExecutionResult


@dataclass(slots=True)
class PlannerSkeleton:
    expression_pattern: str = "unknown"
    require_context: bool = True
    require_bo: bool = False
    require_function: bool = False
    require_local_context: bool = False
    require_global_context: bool = True
    require_namingsql: bool = False
    require_binding: bool = False
    notes: str = ""


@dataclass(slots=True)
class PlannerDetail:
    selected_context_refs: list[str] = field(default_factory=list)
    selected_bo_refs: list[str] = field(default_factory=list)
    selected_function_refs: list[str] = field(default_factory=list)
    selected_namingsql_refs: list[str] = field(default_factory=list)
    param_bindings: dict[str, Any] = field(default_factory=dict)
    plan_payload: dict[str, Any] | None = None
    notes: str = ""


@dataclass(slots=True)
class PlannerWorkingContext:
    compacted_user_query: str
    compacted_node_info: dict[str, Any]
    resource_summaries: dict[str, Any]
    stage_trace: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlannerStageResult:
    success: bool
    payload: Any = None
    errors: list[LLMErrorRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] | None = None


@dataclass(slots=True)
class StubOpenAIClient:
    plan_response: Optional[Dict[str, Any]] = None
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
    ) -> StructuredExecutionResult[ProgramPlan]:
        payload = dict(prompt_params or {})
        self.last_payload = payload
        if stage in self.stage_responses:
            raw_response = self.stage_responses[stage]
        elif stage == "repair":
            raw_response = self.repair_response
        else:
            raw_response = self.plan_response
        parsed = response_parser(raw_response) if raw_response is not None and response_parser is not None else None
        return StructuredExecutionResult(
            parsed=parsed,
            errors=[],
            raw_payload=raw_response,
            attempt=LLMAttemptRecord(
                stage=stage,
                attempt_index=attempt_index,
                request_payload=payload,
                response_payload=raw_response,
                parsed_ok=parsed is not None,
                errors=[],
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

    def plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> ProgramPlan:
        self.plan_attempts = []
        self.repair_attempts = []
        self.llm_errors = []
        working = self._build_working_context(user_requirement=user_requirement, node_def=node_def, env=env)

        skeleton_result = self._run_skeleton_stage(working=working)
        if not skeleton_result.success or skeleton_result.payload is None:
            return self._run_legacy_plan(user_requirement=user_requirement, node_def=node_def, env=env)

        detail_result = self._run_detail_stage(working=working, node_def=node_def, env=env, skeleton=skeleton_result.payload)
        if not detail_result.success or detail_result.payload is None:
            return self._run_legacy_plan(user_requirement=user_requirement, node_def=node_def, env=env)

        assembly_result = self._assemble_final_plan(detail=detail_result.payload)
        if assembly_result.success and assembly_result.payload is not None:
            return assembly_result.payload

        return self._run_legacy_plan(user_requirement=user_requirement, node_def=node_def, env=env)

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
        return execution.parsed

    def _build_working_context(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> PlannerWorkingContext:
        return PlannerWorkingContext(
            compacted_user_query=" ".join(user_requirement.split())[:400],
            compacted_node_info={
                "node_id": node_def.node_id,
                "node_path": node_def.node_path,
                "node_name": node_def.node_name,
                "data_type": node_def.data_type,
                "description": node_def.description,
                "is_ab": node_def.is_ab,
            },
            resource_summaries=self._build_resource_summaries(env),
        )

    def _build_resource_summaries(self, env: FilteredEnvironment) -> dict[str, Any]:
        return {
            "global_context_count": len(env.selected_global_contexts),
            "local_context_count": len(env.visible_local_context.ordered_nodes),
            "bo_count": len(env.selected_bos),
            "function_count": len(env.selected_functions),
            "global_context_paths": [item.path for item in env.selected_global_contexts[:10]],
            "local_context_paths": [item.access_path for item in env.visible_local_context.ordered_nodes[:10]],
            "bo_names": [item.bo_name for item in env.selected_bos[:10]],
            "function_ids": [item.function_id for item in env.selected_functions[:10]],
            "bo_namingsql_ids": [sql_id for item in env.selected_bos[:5] for sql_id in item.naming_sql_ids[:5]],
        }

    def _run_skeleton_stage(self, working: PlannerWorkingContext) -> PlannerStageResult:
        execution = self.client.execute_structured(
            prompt_key="dsl_plan_skeleton_prompt",
            lang=self.prompt_lang,
            prompt_params={
                "planner_context_json": json.dumps(
                    {
                        "user_query": working.compacted_user_query,
                        "node": working.compacted_node_info,
                        "resource_summary": working.resource_summaries,
                    },
                    ensure_ascii=False,
                )
            },
            response_model=None,
            response_parser=self._parse_skeleton_payload,
            stage="plan_skeleton",
            attempt_index=1,
        )
        self.plan_attempts.append(execution.attempt)
        self.llm_errors.extend(execution.errors)
        working.stage_trace.append("plan_skeleton")
        return PlannerStageResult(
            success=execution.parsed is not None,
            payload=execution.parsed,
            errors=execution.errors,
            raw_response=execution.raw_payload,
        )

    def _run_detail_stage(
        self,
        *,
        working: PlannerWorkingContext,
        node_def: NodeDef,
        env: FilteredEnvironment,
        skeleton: PlannerSkeleton,
    ) -> PlannerStageResult:
        detail_env = self._build_detail_env_payload(env=env, skeleton=skeleton)
        execution = self.client.execute_structured(
            prompt_key="dsl_plan_detail_prompt",
            lang=self.prompt_lang,
            prompt_params={
                "user_requirement": working.compacted_user_query,
                "node_def_json": json.dumps(working.compacted_node_info, ensure_ascii=False),
                "skeleton_json": json.dumps(self._skeleton_to_dict(skeleton), ensure_ascii=False),
                "environment_json": json.dumps(detail_env, ensure_ascii=False),
                "node_def": working.compacted_node_info,
                "skeleton": self._skeleton_to_dict(skeleton),
                "environment": detail_env,
            },
            response_model=ProgramPlan,
            response_parser=self._parse_detail_payload,
            stage="plan_detail",
            attempt_index=1,
        )
        self.plan_attempts.append(execution.attempt)
        self.llm_errors.extend(execution.errors)
        working.stage_trace.append("plan_detail")
        return PlannerStageResult(
            success=execution.parsed is not None,
            payload=execution.parsed,
            errors=execution.errors,
            raw_response=execution.raw_payload,
        )

    def _assemble_final_plan(self, detail: PlannerDetail) -> PlannerStageResult:
        if detail.plan_payload is None:
            return PlannerStageResult(success=False, warnings=["detail_missing_plan_payload"])
        parsed = parse_program_plan_payload(detail.plan_payload)
        return PlannerStageResult(
            success=parsed is not None,
            payload=parsed,
            raw_response=detail.plan_payload,
            warnings=[] if parsed is not None else ["assembly_parse_failed"],
        )

    def _run_legacy_plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> ProgramPlan:
        env_payload = self._build_env_payload(env)
        node_payload = {
            "node_id": node_def.node_id,
            "node_path": node_def.node_path,
            "node_name": node_def.node_name,
            "data_type": node_def.data_type,
            "description": node_def.description,
            "is_ab": node_def.is_ab,
            "ab_data_sources": list(node_def.ab_data_sources),
        }
        execution = self.client.execute_structured(
            prompt_key="dsl_plan_prompt",
            lang=self.prompt_lang,
            prompt_params={
                "user_requirement": user_requirement,
                "node_def_json": json.dumps(node_payload, ensure_ascii=False),
                "environment_json": json.dumps(env_payload, ensure_ascii=False),
                "node_def": node_payload,
                "environment": env_payload,
            },
            response_model=ProgramPlan,
            response_parser=parse_program_plan_payload,
            stage="plan",
            attempt_index=1,
        )
        self.plan_attempts.append(execution.attempt)
        self.llm_errors.extend(execution.errors)
        if execution.parsed is not None:
            return execution.parsed
        return self._failed_plan(raw_plan=execution.raw_payload, default_code="plan_generation_failed", errors=execution.errors)

    def _parse_skeleton_payload(self, payload: Dict[str, Any]) -> PlannerSkeleton | None:
        if not isinstance(payload, dict):
            return None
        if "definitions" in payload and "return_expr" in payload:
            inferred = self._infer_skeleton_from_program_plan(payload)
            return inferred
        return PlannerSkeleton(
            expression_pattern=str(payload.get("expression_pattern") or "unknown"),
            require_context=bool(payload.get("require_context", True)),
            require_bo=bool(payload.get("require_bo", False)),
            require_function=bool(payload.get("require_function", False)),
            require_local_context=bool(payload.get("require_local_context", False)),
            require_global_context=bool(payload.get("require_global_context", True)),
            require_namingsql=bool(payload.get("require_namingsql", False)),
            require_binding=bool(payload.get("require_binding", False)),
            notes=str(payload.get("notes") or payload.get("planning_notes") or ""),
        )

    def _parse_detail_payload(self, payload: Dict[str, Any]) -> PlannerDetail | None:
        if not isinstance(payload, dict):
            return None
        if "definitions" in payload and "return_expr" in payload:
            return PlannerDetail(plan_payload=payload)
        plan_payload = payload.get("plan")
        if not isinstance(plan_payload, dict):
            return None
        return PlannerDetail(
            selected_context_refs=list(payload.get("selected_context_refs") or []),
            selected_bo_refs=list(payload.get("selected_bo_refs") or []),
            selected_function_refs=list(payload.get("selected_function_refs") or []),
            selected_namingsql_refs=list(payload.get("selected_namingsql_refs") or []),
            param_bindings=dict(payload.get("param_bindings") or {}),
            plan_payload=plan_payload,
            notes=str(payload.get("notes") or ""),
        )

    def _skeleton_to_dict(self, skeleton: PlannerSkeleton) -> dict[str, Any]:
        return {
            "expression_pattern": skeleton.expression_pattern,
            "require_context": skeleton.require_context,
            "require_bo": skeleton.require_bo,
            "require_function": skeleton.require_function,
            "require_local_context": skeleton.require_local_context,
            "require_global_context": skeleton.require_global_context,
            "require_namingsql": skeleton.require_namingsql,
            "require_binding": skeleton.require_binding,
            "notes": skeleton.notes,
        }

    def _infer_skeleton_from_program_plan(self, payload: dict[str, Any]) -> PlannerSkeleton:
        text = json.dumps(payload, ensure_ascii=False)
        return PlannerSkeleton(
            expression_pattern="query_call" if '"query_call"' in text else ("function_call" if '"function_call"' in text else "expression"),
            require_context='"context_ref"' in text or '"local_ref"' in text,
            require_bo='"query_call"' in text,
            require_function='"function_call"' in text,
            require_local_context='"local_ref"' in text,
            require_global_context='"context_ref"' in text,
            require_namingsql='"naming_sql_id"' in text,
            require_binding='"pairs"' in text or '"args"' in text,
            notes="inferred_from_program_plan",
        )

    def _build_detail_env_payload(self, env: FilteredEnvironment, skeleton: PlannerSkeleton) -> Dict[str, Any]:
        full = self._build_env_payload(env)
        payload: Dict[str, Any] = {
            "selected_global_context_ids": full["selected_global_context_ids"] if skeleton.require_global_context else [],
            "selected_local_context_ids": full["selected_local_context_ids"] if skeleton.require_local_context else [],
            "selected_bo_ids": full["selected_bo_ids"] if skeleton.require_bo else [],
            "selected_function_ids": full["selected_function_ids"] if skeleton.require_function else [],
            "selected_global_contexts": full["selected_global_contexts"] if skeleton.require_global_context else [],
            "selected_local_context_nodes": full["selected_local_context_nodes"] if skeleton.require_local_context else [],
            "selected_bos": full["selected_bos"] if skeleton.require_bo else [],
            "selected_functions": full["selected_functions"] if skeleton.require_function else [],
        }
        if skeleton.require_bo and not skeleton.require_namingsql:
            for bo in payload["selected_bos"]:
                bo["naming_sqls"] = []
        return payload

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
        diagnostics = [
            PlanDiagnostic(
                code=item.code or default_code,
                message=item.message,
                path="raw_plan",
                severity="error",
            )
            for item in errors
        ] or [
            PlanDiagnostic(
                code=default_code,
                message="llm planner returned an invalid response",
                path="raw_plan",
                severity="error",
            )
        ]
        return ProgramPlan(
            definitions=[],
            return_expr=LiteralPlanNode(type="literal", value=None),
            raw_plan=raw_plan or {"fallback": False},
            diagnostics=diagnostics,
        )
