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
    """Minimal validator for rendered DSL integrity checks with shallow shape checks."""

    def validate(
        self,
        generated_dsl: GeneratedDSL,
        request: GenerateDSLRequest,
        env: ResolvedEnvironment,
    ) -> ValidationResult:
        del request, env
        issues: list[ValidationIssue] = []

        if not generated_dsl.value_expression.strip():
            issues.append(
                ValidationIssue(
                    code=ValidationErrorCode.FINAL_EXPRESSION_MISSING,
                    message="Final expression is required.",
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

        issues.extend(self._validate_expression_shapes(generated_dsl.value_expression))

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

        sanitized = re.sub(r"\$ctx\$\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", " ", expression)
        sanitized = re.sub(r"\$local\$\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", " ", sanitized)
        sanitized = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', " ", sanitized)
        sanitized = re.sub(r"\b\d+(?:\.\d+)?\b", " ", sanitized)
        sanitized = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", " ", sanitized)
        sanitized = re.sub(r"\.[A-Za-z_][A-Za-z0-9_]*", " ", sanitized)

        callable_names = {m.group(1) for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", sanitized)}
        tokens = set(_IDENTIFIER_RE.findall(sanitized))

        keywords = {"def", "if", "true", "false", "null", "and", "or", "not", "it", "select", "fetch"}
        candidates = {
            token
            for token in tokens
            if token not in keywords and token not in callable_names and not token.isupper()
        }
        return {candidate for candidate in candidates if candidate not in known_methods}

    def _validate_expression_shapes(self, expression: str) -> list[ValidationIssue]:
        """Apply small shape checks for IF and binary expressions."""

        issues: list[ValidationIssue] = []
        if not expression:
            return issues

        for inside in self._extract_call_contents(expression, "if"):
            args = self._split_top_level_args(inside)
            if len(args) != 3:
                issues.append(
                    ValidationIssue(
                        code=ValidationErrorCode.FINAL_EXPRESSION_MISSING,
                        message="IF expression requires exactly 3 arguments.",
                        location="value_expression",
                    )
                )

        binary_ops = ("==", "!=", ">=", "<=", ">", "<")
        for op in binary_ops:
            if op not in expression:
                continue
            if re.search(rf"(^|[,(])\s*{re.escape(op)}\s*", expression) or re.search(
                rf"{re.escape(op)}\s*([,)])", expression
            ):
                issues.append(
                    ValidationIssue(
                        code=ValidationErrorCode.FINAL_EXPRESSION_MISSING,
                        message="Binary expression requires both left and right operands.",
                        location="value_expression",
                    )
                )
                break

        return issues

    @staticmethod
    def _extract_call_contents(expression: str, name: str) -> list[str]:
        """Extract the inner text of named function calls with balanced parentheses."""

        pattern = f"{name}("
        contents: list[str] = []
        search_start = 0
        while True:
            start = expression.find(pattern, search_start)
            if start < 0:
                return contents
            idx = start + len(pattern)
            depth = 1
            chunk_start = idx
            while idx < len(expression) and depth > 0:
                char = expression[idx]
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                idx += 1
            if depth == 0:
                contents.append(expression[chunk_start : idx - 1])
                search_start = idx
            else:
                contents.append(expression[chunk_start:])
                return contents

    @staticmethod
    def _split_top_level_args(text: str) -> list[str]:
        """Split comma-separated args while respecting nested parentheses."""

        parts: list[str] = []
        current: list[str] = []
        depth = 0
        for char in text:
            if char == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    parts.append(item)
                current = []
                continue
            if char == "(":
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
            current.append(char)

        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts
