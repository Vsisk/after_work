"""Explanation builder protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.common import StructuredExplanation
from billing_dsl_agent.types.dsl import ValuePlan
from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.plan import ResourceBinding


class ExplanationBuilder(Protocol):
    """Build a structured explanation for generated DSL."""

    def build(
        self,
        intent: NodeIntent,
        binding: ResourceBinding,
        plan: ValuePlan,
    ) -> StructuredExplanation:
        ...
