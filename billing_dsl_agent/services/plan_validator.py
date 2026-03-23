"""Local validation for LLM-proposed execution plans."""

from __future__ import annotations

from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.validation import ValidationErrorCode, ValidationIssue, ValidationResult


class PlanValidator:
    """Validate explicit plan references against the local environment."""

    def validate(self, plan: PlanDraft, env: ResolvedEnvironment) -> ValidationResult:
        issues: list[ValidationIssue] = []

        for ref in plan.context_refs or []:
            issue = self._validate_context_ref(ref, env)
            if issue is not None:
                issues.append(issue)

        for bo_ref in plan.bo_refs or []:
            issues.extend(self._validate_bo_ref(bo_ref, env))

        for function_ref in plan.function_refs or []:
            if self._match_function(function_ref, env.available_functions) is None:
                issues.append(
                    ValidationIssue(
                        code=ValidationErrorCode.UNKNOWN_FUNCTION,
                        message=f"Unknown function reference: {function_ref}",
                        location=f"function:{function_ref}",
                    )
                )

        if not self._is_supported_expression(plan):
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.UNSATISFIED_RESOURCE,
                    message=f"Unsupported expression pattern: {plan.expression_pattern or '<empty>'}",
                    location="expression_pattern",
                )
            )

        has_error = any(issue.level == "error" for issue in issues)
        return ValidationResult(syntax_valid=not has_error, semantic_valid=not has_error, issues=issues)

    def _validate_context_ref(self, ref: str, env: ResolvedEnvironment) -> ValidationIssue | None:
        parts = [item for item in str(ref or "").split(".") if item]
        if len(parts) < 2:
            return ValidationIssue(
                code=ValidationErrorCode.UNKNOWN_CONTEXT_VAR,
                message=f"Invalid context reference: {ref}",
                location=f"context:{ref}",
            )

        prefix = parts[0]
        var_name = parts[1]
        field_name = parts[2] if len(parts) > 2 else None

        if prefix == "$ctx$":
            scope = ContextScope.GLOBAL
            vars_ = env.global_context_vars
            error_code = ValidationErrorCode.UNKNOWN_CONTEXT_VAR
        elif prefix == "$local$":
            scope = ContextScope.LOCAL
            vars_ = env.local_context_vars
            error_code = ValidationErrorCode.UNKNOWN_LOCAL_VAR
        else:
            return ValidationIssue(
                code=ValidationErrorCode.UNKNOWN_CONTEXT_VAR,
                message=f"Invalid context prefix in ref: {ref}",
                location=f"context:{ref}",
            )

        matched_var = next((item for item in vars_ if item.name == var_name), None)
        if matched_var is None:
            return ValidationIssue(
                code=error_code,
                message=f"Unknown {scope.value.lower()} context var: {var_name}",
                location=f"context:{ref}",
            )

        if field_name and not any(field.name == field_name for field in matched_var.fields or []):
            return ValidationIssue(
                code=error_code,
                message=f"Unknown field `{field_name}` on context `{var_name}`",
                location=f"context:{ref}",
            )

        return None

    def _validate_bo_ref(self, bo_ref: dict[str, object], env: ResolvedEnvironment) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        bo_name = str(bo_ref.get("bo_name") or bo_ref.get("name") or "").strip()
        if not bo_name:
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.UNKNOWN_BO,
                    message="Missing bo_name in plan.",
                    location="bo_ref",
                )
            )
            return issues

        bo = self._match_bo(bo_name, env.available_bos)
        if bo is None:
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.UNKNOWN_BO,
                    message=f"Unknown BO reference: {bo_name}",
                    location=f"bo:{bo_name}",
                )
            )
            return issues

        field_candidates: list[str] = []
        direct_field = str(bo_ref.get("field") or bo_ref.get("target_field") or "").strip()
        if direct_field:
            field_candidates.append(direct_field)
        for field_name in bo_ref.get("selected_field_names") or []:
            text = str(field_name).strip()
            if text:
                field_candidates.append(text)

        for field_name in field_candidates:
            if not any(field.name == field_name for field in bo.fields or []):
                issues.append(
                    ValidationIssue(
                        code=ValidationErrorCode.UNKNOWN_BO_FIELD,
                        message=f"Unknown field `{field_name}` on BO `{bo_name}`",
                        location=f"bo:{bo_name}.{field_name}",
                    )
                )

        return issues

    @staticmethod
    def _is_supported_expression(plan: PlanDraft) -> bool:
        pattern = str(plan.expression_pattern or "").strip().lower()
        if not pattern:
            return bool(plan.context_refs or plan.bo_refs or plan.function_refs)
        if pattern in {"direct_ref", "query(field)", "function_call(value)"}:
            return True
        if "if(" in pattern:
            return bool(plan.context_refs) and "condition_value" in (plan.semantic_slots or {})
        return bool(plan.context_refs or plan.bo_refs or plan.function_refs)

    @staticmethod
    def _match_bo(bo_name: str, available_bos: list[BODef]) -> BODef | None:
        normalized = bo_name.strip().lower()
        return next((bo for bo in available_bos if bo.name.strip().lower() == normalized), None)

    @staticmethod
    def _match_function(function_ref: str, available_functions: list[FunctionDef]) -> FunctionDef | None:
        normalized = function_ref.strip().lower()
        exact = next((fn for fn in available_functions if fn.full_name.strip().lower() == normalized), None)
        if exact is not None:
            return exact
        method_matches = [fn for fn in available_functions if fn.method_name.strip().lower() == normalized]
        if len(method_matches) == 1:
            return method_matches[0]
        return None
