"""Explanation builder protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.common import StructuredExplanation
from billing_dsl_agent.types.dsl import ValuePlan


class ExplanationBuilder(Protocol):
    """Build a structured explanation for generated DSL."""

    def build(
        self,
        plan_draft: PlanDraft,
        plan: ValuePlan,
    ) -> StructuredExplanation:
        ...
