from __future__ import annotations

from typing import Optional

from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import FilteredEnvironment, PlanDraft, ValidationResult


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

    def validate(self, plan: PlanDraft, env: FilteredEnvironment) -> ValidationResult:
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

    def _collect_issues(self, plan: PlanDraft, env: FilteredEnvironment) -> list[str]:
        issues: list[str] = []
        registry = env.registry
        filtered_contexts = set(env.selected_global_context_ids) | set(env.selected_local_context_ids)
        filtered_bos = set(env.selected_bo_ids)
        filtered_functions = set(env.selected_function_ids)

        if plan.expression_pattern not in self.ALLOWED_PATTERNS:
            issues.append(f"unsupported expression_pattern: {plan.expression_pattern}")

        for context_id in plan.context_refs:
            if context_id not in registry.contexts:
                issues.append(f"unknown context id: {context_id}")
                continue
            if context_id not in filtered_contexts:
                issues.append(f"context not in filtered environment: {context_id}")

        for bo_ref in plan.bo_refs:
            bo_id = str(bo_ref.get("bo_id") or "").strip()
            if bo_id not in registry.bos:
                issues.append(f"unknown bo id: {bo_id or '<empty>'}")
                continue
            if bo_id not in filtered_bos:
                issues.append(f"bo not in filtered environment: {bo_id}")

            bo = registry.bos[bo_id]
            field_id = str(bo_ref.get("field_id") or "").strip()
            if field_id and field_id not in bo.field_ids:
                issues.append(f"unknown bo field id: {field_id}")

            for item in bo_ref.get("field_ids") or []:
                if str(item) not in bo.field_ids:
                    issues.append(f"unknown bo field id: {item}")

            data_source = str(bo_ref.get("data_source") or "").strip()
            if data_source and bo.data_source and data_source != bo.data_source:
                issues.append(f"bo data source mismatch: {bo_id}")

            naming_sql_id = str(bo_ref.get("naming_sql_id") or "").strip()
            if naming_sql_id and naming_sql_id not in bo.naming_sql_ids:
                issues.append(f"unknown naming sql id: {naming_sql_id}")

            for param in bo_ref.get("params") or []:
                value = str(param.get("value") or "").strip()
                if not value:
                    issues.append(f"empty namingSQL param value: {bo_id}.{param.get('param_name', '')}")
                    continue
                source_type = str(param.get("value_source_type") or "").strip()
                if source_type not in self.ALLOWED_PARAM_SOURCE:
                    issues.append(f"invalid value_source_type: {source_type}")
                if source_type == "context" and value not in filtered_contexts:
                    issues.append(f"param context not in filtered environment: {value}")

        for function_id in plan.function_refs:
            if function_id not in registry.functions:
                issues.append(f"unknown function id: {function_id}")
                continue
            if function_id not in filtered_functions:
                issues.append(f"function not in filtered environment: {function_id}")
                continue
            expected = registry.functions[function_id].params
            actual_args = plan.semantic_slots.get("function_args") or []
            if isinstance(actual_args, list) and expected and len(actual_args) != len(expected):
                issues.append(f"function args mismatch: {function_id} expected {len(expected)} got {len(actual_args)}")

        return issues
