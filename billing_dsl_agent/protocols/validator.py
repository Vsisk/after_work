"""Validator protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.common import GeneratedDSL
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.request_response import GenerateDSLRequest
from billing_dsl_agent.types.validation import ValidationResult


class Validator(Protocol):
    """Validate generated DSL result."""

    def validate(
        self,
        generated_dsl: GeneratedDSL,
        request: GenerateDSLRequest,
        env: ResolvedEnvironment,
    ) -> ValidationResult:
        ...
