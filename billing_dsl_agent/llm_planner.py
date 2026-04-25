from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from billing_dsl_agent.log_utils import dumps_for_log, get_logger
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

logger = get_logger(__name__)

PLAN_PROMPT_KEY = "dsl_plan_prompt"
REPAIR_PROMPT_KEY = "dsl_repair_prompt"


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
        raw_response = None
        if stage == "plan":
            raw_response = self.plan_response
        if stage == "repair":
            raw_response = self.repair_response

        parsed = None
        errors: list[LLMErrorRecord] = []
        if raw_response is not None:
            try:
                parsed = response_parser(raw_response) if response_parser else response_model.model_validate(raw_response)
            except Exception as exc:
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

    def plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> ProgramPlan:
        self.plan_attempts = []
        self.repair_attempts = []
        self.llm_errors = []
        logger.info(
            "planner_started user_requirement=%s node_id=%s node_path=%s",
            user_requirement,
            node_def.node_id,
            node_def.node_path,
        )
        return self._execute_plan(user_requirement=user_requirement, node_def=node_def, env=env)

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
            prompt_key=REPAIR_PROMPT_KEY,
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

    def _execute_plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> ProgramPlan:
        env_payload = self._build_env_payload(env)
        node_payload = node_def.model_dump(mode="python")
        last_raw_response: dict[str, Any] | None = None
        last_errors: list[LLMErrorRecord] = []
        retry_guidance = ""
        for attempt_index in (1, 2):
            execution = self.client.execute_structured(
                prompt_key=PLAN_PROMPT_KEY,
                lang=self.prompt_lang,
                prompt_params={
                    "user_requirement": user_requirement,
                    "user_query": user_requirement,
                    "node_def_json": json.dumps(node_payload, ensure_ascii=False),
                    "environment_json": json.dumps(env_payload, ensure_ascii=False),
                    "node_def": node_payload,
                    "environment": env_payload,
                    "retry_guidance": retry_guidance or "None",
                },
                response_model=ProgramPlan,
                response_parser=parse_program_plan_payload,
                stage="plan",
                attempt_index=attempt_index,
            )
            self.plan_attempts.append(execution.attempt)
            self.llm_errors.extend(execution.errors)
            last_raw_response = execution.raw_payload
            last_errors = list(execution.errors)
            if execution.parsed is not None and not execution.errors:
                return execution.parsed
            if not last_errors:
                last_errors = [
                    LLMErrorRecord(
                        stage="plan",
                        code="plan_parse_failed",
                        message="planner returned no parseable ProgramPlan",
                        raw_payload=execution.raw_payload,
                    )
                ]
                self.llm_errors.extend(last_errors)
            retry_guidance = "Return a valid ProgramPlan JSON object with definitions and return_expr only."

        return self._failed_plan(raw_plan=last_raw_response, errors=last_errors)

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

    def _failed_plan(self, raw_plan: Dict[str, Any] | None, errors: list[LLMErrorRecord]) -> ProgramPlan:
        diagnostics = [
            PlanDiagnostic(
                code=item.code or "plan_failed",
                message=item.message,
                path=item.stage or "raw_plan",
                severity="error",
            )
            for item in errors
        ]
        if not diagnostics:
            diagnostics = [
                PlanDiagnostic(
                    code="plan_failed",
                    message="llm planner returned an invalid response",
                    path="raw_plan",
                    severity="error",
                )
            ]
        return ProgramPlan(
            definitions=[],
            return_expr=LiteralPlanNode(type="literal", value=None),
            raw_plan=raw_plan,
            diagnostics=diagnostics,
        )
