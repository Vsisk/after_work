from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from billing_dsl_agent.models import (
    FilteredEnvironment,
    LiteralPlanNode,
    NodeDef,
    PlanDiagnostic,
    ProgramPlan,
    ValidationIssue,
)
from billing_dsl_agent.plan_validator import parse_program_plan_payload


class OpenAIClient(Protocol):
    def create_plan(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ...


@dataclass(slots=True)
class StubOpenAIClient:
    plan_response: Optional[Dict[str, Any]] = None
    repair_response: Optional[Dict[str, Any]] = None
    last_payload: Optional[Dict[str, Any]] = None

    def create_plan(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.last_payload = payload
        if payload.get("mode") == "repair":
            return self.repair_response
        return self.plan_response


class LLMPlanner:
    def __init__(self, client: OpenAIClient):
        self.client = client
        self.prompt_dir = Path(__file__).resolve().parent / "prompts"

    def plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> ProgramPlan:
        payload = {
            "mode": "plan",
            "prompt": self._load_prompt("plan_prompt.txt"),
            "user_requirement": user_requirement,
            "node_def": {
                "node_id": node_def.node_id,
                "node_path": node_def.node_path,
                "node_name": node_def.node_name,
                "data_type": node_def.data_type,
                "is_ab": node_def.is_ab,
            },
            "environment": self._build_env_payload(env),
        }
        raw = self.client.create_plan(payload)
        if raw is None:
            return ProgramPlan(
                definitions=[],
                return_expr=LiteralPlanNode(type="literal", value=None),
                raw_plan={"fallback": True},
                diagnostics=[
                    PlanDiagnostic(
                        code="planner_fallback",
                        message="planner returned no result; fallback literal plan used",
                    )
                ],
            )
        return self._parse_plan(raw)

    def repair(
        self,
        invalid_plan: ProgramPlan,
        env: FilteredEnvironment,
        issues: list[ValidationIssue],
    ) -> Optional[ProgramPlan]:
        payload = {
            "mode": "repair",
            "prompt": self._load_prompt("repair_prompt.txt"),
            "invalid_plan": invalid_plan.raw_plan or invalid_plan.model_dump(mode="python"),
            "issues": [item.model_dump(mode="python") for item in issues],
            "environment": self._build_env_payload(env),
        }
        raw = self.client.create_plan(payload)
        if raw is None:
            return None
        return self._parse_plan(raw)

    def _build_env_payload(self, env: FilteredEnvironment) -> Dict[str, Any]:
        return {
            "selected_global_context_ids": env.selected_global_context_ids,
            "selected_local_context_ids": env.selected_local_context_ids,
            "selected_bo_ids": env.selected_bo_ids,
            "selected_function_ids": env.selected_function_ids,
        }

    def _load_prompt(self, name: str) -> str:
        return (self.prompt_dir / name).read_text(encoding="utf-8").strip()

    def _parse_plan(self, raw: Dict[str, Any]) -> ProgramPlan:
        try:
            return parse_program_plan_payload(raw)
        except Exception as exc:
            return ProgramPlan(
                definitions=[],
                return_expr=LiteralPlanNode(type="literal", value=None),
                raw_plan=raw,
                diagnostics=[
                    PlanDiagnostic(
                        code="plan_parse_error",
                        message=str(exc),
                        path="raw_plan",
                        severity="error",
                    )
                ],
            )
