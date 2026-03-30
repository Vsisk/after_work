from __future__ import annotations

import json
from dataclasses import dataclass
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
class StubOpenAIClient:
    plan_response: Optional[Dict[str, Any]] = None
    repair_response: Optional[Dict[str, Any]] = None
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
        raw_response = self.repair_response if stage == "repair" else self.plan_response
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
        return self._failed_plan(
            raw_plan=execution.raw_payload,
            default_code="plan_generation_failed",
            errors=execution.errors,
        )

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
            "selected_local_contexts": [
                {
                    "resource_id": item.resource_id,
                    "path": item.path,
                    "name": item.name,
                    "description": item.description,
                    "scope": item.scope,
                }
                for item in env.selected_local_contexts
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
