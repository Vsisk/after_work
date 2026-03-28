from __future__ import annotations

import re
from dataclasses import dataclass

from billing_dsl_agent.models import FilteredEnvironment, ValidationIssue


CONTEXT_PATH_RE = re.compile(r"^\$ctx\$\.[A-Za-z_][A-Za-z0-9_$.]*$")
LITERAL_STRING_RE = re.compile(r'^".*"$|^\'.*\'$')
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
FORBIDDEN_VALUES = {"", "null", "none", "unknown", "tbd", "fake", "fake path"}


@dataclass(slots=True)
class ExpressionRefValidator:
    def validate(self, expression: str | None, env: FilteredEnvironment, path: str) -> list[ValidationIssue]:
        if expression is None:
            return [ValidationIssue(code="expression_null", message="expression is null", path=path)]

        value = expression.strip()
        if value.lower() in FORBIDDEN_VALUES:
            return [ValidationIssue(code="expression_forbidden_value", message=f"forbidden expression value: {value}", path=path)]

        if CONTEXT_PATH_RE.match(value):
            known_paths = {resource.path for resource in env.registry.contexts.values()}
            if value not in known_paths:
                return [ValidationIssue(code="unknown_context_ref", message=f"unknown context ref: {value}", path=path)]
            return []

        if LITERAL_STRING_RE.match(value) or NUMERIC_RE.match(value):
            return []

        return [
            ValidationIssue(
                code="invalid_expression_ref",
                message=f"invalid expression format: {value}",
                path=path,
            )
        ]

