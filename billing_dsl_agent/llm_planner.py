from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from billing_dsl_agent.models import PlanDraft


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

    def plan(self, user_query: str, node_info: Any, candidate_set_or_env: Any) -> PlanDraft:
        payload = {
            "mode": "plan",
            "prompt": self._load_prompt("plan_prompt.txt"),
            "user_requirement": user_query,
            "node_info": self._normalize_node_info(node_info),
            "candidate_resources": self._normalize_candidate_payload(candidate_set_or_env),
        }
        raw = self.client.create_plan(payload)
        if raw is None:
            return PlanDraft(intent_summary="", expression_pattern="direct_ref", raw_plan={"fallback": True})
        return self._parse_plan(raw)

    def repair(self, invalid_plan: PlanDraft, environment: Any, issues: list[str]) -> Optional[PlanDraft]:
        payload = {
            "mode": "repair",
            "prompt": self._load_prompt("repair_prompt.txt"),
            "invalid_plan": invalid_plan.raw_plan or self._to_dict(invalid_plan),
            "issues": issues,
            "environment": {
                "context_paths": list(getattr(environment, "context_paths", []) or []),
                "bo_schema": dict(getattr(environment, "bo_schema", {}) or {}),
                "function_schema": list(getattr(environment, "function_schema", []) or []),
                "available_functions": self._available_functions(list(getattr(environment, "function_schema", []) or [])),
            },
        }
        raw = self.client.create_plan(payload)
        if raw is None:
            return None
        return self._parse_plan(raw)

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

    def _available_functions(self, function_schema: list[Any]) -> list[Dict[str, Any]]:
        available: list[Dict[str, Any]] = []
        for item in function_schema:
            if isinstance(item, str):
                available.append({"name": item, "params": []})
                continue
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or item.get("name") or "").strip()
            if not full_name:
                continue
            params = item.get("params") or item.get("param_list") or []
            if isinstance(params, list):
                parsed_params: list[str] = []
                for p in params:
                    if isinstance(p, str):
                        parsed_params.append(p)
                    elif isinstance(p, dict):
                        param_name = str(p.get("param_name") or p.get("name") or "").strip()
                        if param_name:
                            parsed_params.append(param_name)
                available.append({"name": full_name, "params": parsed_params})
            else:
                available.append({"name": full_name, "params": []})
        return available

    def _normalize_node_info(self, node_info: Any) -> Dict[str, Any]:
        if isinstance(node_info, dict):
            return dict(node_info)
        return {
            "node_id": str(getattr(node_info, "node_id", "")),
            "node_path": str(getattr(node_info, "node_path", "")),
            "node_name": str(getattr(node_info, "node_name", "")),
            "description": str(getattr(node_info, "description", "")),
            "data_type": str(getattr(node_info, "data_type", "")),
        }

    def _normalize_candidate_payload(self, candidate_set_or_env: Any) -> Dict[str, Any]:
        if hasattr(candidate_set_or_env, "context_candidates"):
            return {
                "context_candidates": [
                    {
                        "path": str(getattr(item, "path", "")),
                        "name": str(getattr(item, "name", "")),
                        "description": str(getattr(item, "description", "")),
                    }
                    for item in list(getattr(candidate_set_or_env, "context_candidates", []) or [])
                ],
                "bo_candidates": [
                    {
                        "bo_name": str(getattr(item, "bo_name", "")),
                        "description": str(getattr(item, "description", "")),
                        "fields": list(getattr(item, "fields", []) or []),
                        "naming_sqls": list(getattr(item, "naming_sqls", []) or []),
                    }
                    for item in list(getattr(candidate_set_or_env, "bo_candidates", []) or [])
                ],
                "function_candidates": [
                    {
                        "name": str(getattr(item, "full_name", "")),
                        "description": str(getattr(item, "description", "")),
                        "params": list(getattr(item, "params", []) or []),
                    }
                    for item in list(getattr(candidate_set_or_env, "function_candidates", []) or [])
                ],
            }

        context_paths = list(getattr(candidate_set_or_env, "context_paths", []) or [])
        bo_schema = dict(getattr(candidate_set_or_env, "bo_schema", {}) or {})
        function_schema = list(getattr(candidate_set_or_env, "function_schema", []) or [])
        return {
            "context_candidates": [{"path": p, "name": p.split(".")[-1], "description": ""} for p in context_paths],
            "bo_candidates": [
                {"bo_name": k, "description": "", "fields": list(v), "naming_sqls": []}
                for k, v in bo_schema.items()
            ],
            "function_candidates": self._available_functions(function_schema),
        }
