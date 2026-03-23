from __future__ import annotations

from typing import Optional

from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import Environment, PlanDraft, ValidationResult


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

    def validate(self, plan: PlanDraft, env: Environment) -> ValidationResult:
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

    def _collect_issues(self, plan: PlanDraft, env: Environment) -> list[str]:
        issues: list[str] = []
        if plan.expression_pattern not in self.ALLOWED_PATTERNS:
            issues.append(f"unsupported expression_pattern: {plan.expression_pattern}")

        for ctx in plan.context_refs:
            if ctx not in env.context_paths:
                issues.append(f"fake context path: {ctx}")

        for ref in plan.bo_refs:
            bo_name = str(ref.get("bo_name") or "").strip()
            if not bo_name or bo_name not in env.bo_schema:
                issues.append(f"unknown bo: {bo_name or '<empty>'}")
                continue

            field = str(ref.get("field") or ref.get("target_field") or "").strip()
            if field and field not in env.bo_schema.get(bo_name, []):
                issues.append(f"unknown bo field: {bo_name}.{field}")

            for selected in ref.get("selected_fields") or ref.get("selected_field_names") or []:
                s = str(selected).strip()
                if s and s not in env.bo_schema.get(bo_name, []):
                    issues.append(f"unknown bo field: {bo_name}.{s}")

            for param in ref.get("params") or []:
                value = str(param.get("value") or "").strip()
                if not value:
                    issues.append(f"empty namingSQL param value: {bo_name}.{param.get('param_name', '')}")
                    continue
                source_type = str(param.get("value_source_type") or "").strip()
                if source_type not in self.ALLOWED_PARAM_SOURCE:
                    issues.append(f"invalid value_source_type: {source_type}")
                if source_type == "context" and value not in env.context_paths:
                    issues.append(f"fake context path in param: {value}")

        for fn_name in plan.function_refs:
            if fn_name not in env.function_schema:
                issues.append(f"unknown function: {fn_name}")

        return issues
