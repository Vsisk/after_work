"""Default validator service."""

from __future__ import annotations

import re
from collections import Counter

from billing_dsl_agent.types.common import GeneratedDSL
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.request_response import GenerateDSLRequest
from billing_dsl_agent.types.validation import ValidationErrorCode, ValidationIssue, ValidationResult

_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


class DefaultValidator:
    """Minimal validator for rendered DSL integrity checks with shallow ref checks."""

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

        method_names = [method.name for method in generated_dsl.methods]
        name_counter = Counter(method_names)
        for name, count in name_counter.items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        code=ValidationErrorCode.DUPLICATE_METHOD_NAME,
                        message=f"Duplicate method name: {name}",
                        location=f"method:{name}",
                    )
                )

        known_methods = set(method_names)
        unknown_method_refs = self._find_unknown_method_refs(
            generated_dsl=generated_dsl,
            known_methods=known_methods,
        )
        for ref in sorted(unknown_method_refs):
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.UNKNOWN_METHOD_REF,
                    message=f"Unknown method reference: {ref}",
                    location="value_expression",
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

        # TODO: validate context/local references against resolved environment.
        # TODO: validate BO/query usage and namingSQL availability.
        # TODO: validate function resolution and import requirements.
        # TODO: add method-cycle checks once plan-level AST is threaded here.

        has_error = any(issue.level == "error" for issue in issues)
        return ValidationResult(syntax_valid=not has_error, semantic_valid=not has_error, issues=issues)

    def _find_unknown_method_refs(self, generated_dsl: GeneratedDSL, known_methods: set[str]) -> set[str]:
        unknown: set[str] = set()

        for method in generated_dsl.methods:
            unknown.update(self._extract_unknown_identifiers(method.body, known_methods))

        unknown.update(self._extract_unknown_identifiers(generated_dsl.value_expression, known_methods))
        return unknown

    def _extract_unknown_identifiers(self, expression: str, known_methods: set[str]) -> set[str]:
        if not expression:
            return set()

        # Remove context/local references and field accesses to reduce false positives.
        sanitized = re.sub(r"\$ctx\$\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", " ", expression)
        sanitized = re.sub(r"\$local\$\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", " ", sanitized)
        sanitized = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', " ", sanitized)
        sanitized = re.sub(r"\b\d+(?:\.\d+)?\b", " ", sanitized)
        sanitized = re.sub(r"\.[A-Za-z_][A-Za-z0-9_]*", " ", sanitized)

        # Remove function calls; keep identifiers not followed by '(' as method-ref candidates.
        callable_names = {m.group(1) for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", sanitized)}
        tokens = set(_IDENTIFIER_RE.findall(sanitized))

        keywords = {"def", "if", "true", "false", "null", "and", "or", "not", "it"}
        candidates = {
            t
            for t in tokens
            if t not in keywords
            and t not in callable_names
            and not t.isupper()
        }

        return {c for c in candidates if c not in known_methods}
