"""Default validator service."""

from __future__ import annotations

from collections import Counter

from billing_dsl_agent.types.common import GeneratedDSL
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.request_response import GenerateDSLRequest
from billing_dsl_agent.types.validation import ValidationErrorCode, ValidationIssue, ValidationResult


class DefaultValidator:
    """Minimal validator for rendered DSL integrity checks."""

    def validate(
        self,
        generated_dsl: GeneratedDSL,
        request: GenerateDSLRequest,
        env: ResolvedEnvironment,
    ) -> ValidationResult:
        del request, env  # reserved for future semantic checks
        issues: list[ValidationIssue] = []

        if not generated_dsl.value_expression.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.FINAL_EXPRESSION_MISSING,
                    message="Final expression is required.",
                    location="value_expression",
                )
            )

        name_counter = Counter(method.name for method in generated_dsl.methods)
        for name, count in name_counter.items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        code=ValidationErrorCode.DUPLICATE_METHOD_NAME,
                        message=f"Duplicate method name: {name}",
                        location=f"method:{name}",
                    )
                )

        rendered_text = generated_dsl.to_text().strip()
        if not rendered_text:
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.FINAL_EXPRESSION_MISSING,
                    message="Rendered DSL text is empty.",
                )
            )

        # TODO: validate unknown context/local references against env.
        # TODO: validate BO/query usage and namingSQL availability.
        # TODO: validate function resolution and import requirements.

        has_error = any(issue.level == "error" for issue in issues)
        return ValidationResult(syntax_valid=not has_error, semantic_valid=not has_error, issues=issues)
