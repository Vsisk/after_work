from __future__ import annotations

from typing import Any, Dict, Optional

from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import PlanDraft, ValidationResult


class PlanValidator:
    ALLOWED_PATTERNS = {
        "direct_ref",
        "if",
        "select_one",
        "select",
        "fetch_one",
        "fetch",
        "function_call",
    }
    ALLOWED_PARAM_SOURCE = {"context", "constant"}

    def __init__(self, planner: Optional[LLMPlanner] = None, max_retries: int = 2):
        self.planner = planner
        self.max_retries = max_retries

    def validate(self, plan: PlanDraft, env: Any) -> ValidationResult:
        current = plan
        attempts = 0
        while True:
            issues = self._collect_issues(current, env)
            if not issues:
                return ValidationResult(is_valid=True, issues=[], repaired_plan=current)
            if self.planner is None or attempts >= self.max_retries:
                return ValidationResult(is_valid=False, issues=issues, repaired_plan=current)
            repaired = self.planner.repair(current, env, issues)
            if repaired is None:
                return ValidationResult(is_valid=False, issues=issues, repaired_plan=current)
            current = repaired
            attempts += 1

    def _collect_issues(self, plan: PlanDraft, env: Any) -> list[str]:
        issues: list[str] = []
        context_paths = set(list(getattr(env, "context_paths", []) or []))
        bo_schema = dict(getattr(env, "bo_schema", {}) or {})
        function_catalog = self._build_function_catalog(list(getattr(env, "function_schema", []) or []))

        if plan.expression_pattern not in self.ALLOWED_PATTERNS:
            issues.append(f"unsupported expression_pattern: {plan.expression_pattern}")

        for ctx in plan.context_refs:
            if ctx not in context_paths:
                issues.append(f"fake context path: {ctx}")

        for ref in plan.bo_refs:
            bo_name = str(ref.get("bo_name") or "").strip()
            if not bo_name or bo_name not in bo_schema:
                issues.append(f"unknown bo: {bo_name or '<empty>'}")
                continue

            field = str(ref.get("field") or ref.get("target_field") or "").strip()
            if field and field not in bo_schema.get(bo_name, []):
                issues.append(f"unknown bo field: {bo_name}.{field}")

            for selected in ref.get("selected_fields") or ref.get("selected_field_names") or []:
                s = str(selected).strip()
                if s and s not in bo_schema.get(bo_name, []):
                    issues.append(f"unknown bo field: {bo_name}.{s}")

            for param in ref.get("params") or []:
                value = str(param.get("value") or "").strip()
                if not value:
                    issues.append(f"empty namingSQL param value: {bo_name}.{param.get('param_name', '')}")
                    continue
                source_type = str(param.get("value_source_type") or "").strip()
                if source_type not in self.ALLOWED_PARAM_SOURCE:
                    issues.append(f"invalid value_source_type: {source_type}")
                if source_type == "context" and value not in context_paths:
                    issues.append(f"fake context path in param: {value}")

        for fn_name in plan.function_refs:
            if fn_name not in function_catalog:
                issues.append(f"unknown function: {fn_name}")
                continue
            expected = function_catalog.get(fn_name, [])
            actual_args = plan.semantic_slots.get("function_args") or []
            if isinstance(actual_args, list) and expected and len(actual_args) != len(expected):
                issues.append(f"function args mismatch: {fn_name} expected {len(expected)} got {len(actual_args)}")

        return issues

    def _build_function_catalog(self, function_schema: list[Any]) -> Dict[str, list[str]]:
        catalog: Dict[str, list[str]] = {}
        for item in function_schema:
            if isinstance(item, str):
                catalog[item] = []
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("full_name") or item.get("name") or "").strip()
            if not name:
                continue
            params = item.get("params") or item.get("param_list") or []
            parsed_params: list[str] = []
            if isinstance(params, list):
                for p in params:
                    if isinstance(p, str):
                        parsed_params.append(p)
                    elif isinstance(p, dict):
                        param_name = str(p.get("param_name") or p.get("name") or "").strip()
                        if param_name:
                            parsed_params.append(param_name)
            catalog[name] = parsed_params
        return catalog
