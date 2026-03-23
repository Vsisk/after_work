from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from billing_dsl_agent.models import FilteredEnvironment, NodeDef, PlanDraft


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

    def plan(self, user_requirement: str, node_def: NodeDef, env: FilteredEnvironment) -> PlanDraft:
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
            return PlanDraft(intent_summary="", expression_pattern="direct_ref", raw_plan={"fallback": True})
        return self._parse_plan(raw)

    def repair(self, invalid_plan: PlanDraft, env: FilteredEnvironment, issues: list[str]) -> Optional[PlanDraft]:
        payload = {
            "mode": "repair",
            "prompt": self._load_prompt("repair_prompt.txt"),
            "invalid_plan": invalid_plan.raw_plan or self._to_dict(invalid_plan),
            "issues": issues,
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

    @staticmethod
    def _to_dict(plan: PlanDraft) -> Dict[str, Any]:
        return {
            "intent_summary": plan.intent_summary,
            "expression_pattern": plan.expression_pattern,
            "context_refs": plan.context_refs,
            "bo_refs": plan.bo_refs,
            "function_refs": plan.function_refs,
            "semantic_slots": plan.semantic_slots,
            "raw_plan": plan.raw_plan,
        }

    def _load_prompt(self, name: str) -> str:
        return (self.prompt_dir / name).read_text(encoding="utf-8").strip()

    def _parse_plan(self, raw: Dict[str, Any]) -> PlanDraft:
        data = dict(raw)
        if isinstance(data.get("raw_plan"), str):
            try:
                data["raw_plan"] = json.loads(data["raw_plan"])
            except json.JSONDecodeError:
                data["raw_plan"] = {"raw": data["raw_plan"]}
        return PlanDraft(
            intent_summary=str(data.get("intent_summary") or ""),
            expression_pattern=str(data.get("expression_pattern") or ""),
            context_refs=[str(v) for v in data.get("context_refs") or []],
            bo_refs=[dict(v) for v in data.get("bo_refs") or [] if isinstance(v, dict)],
            function_refs=[str(v) for v in data.get("function_refs") or []],
            semantic_slots=dict(data.get("semantic_slots") or {}),
            raw_plan=dict(data.get("raw_plan") or data),
        )
