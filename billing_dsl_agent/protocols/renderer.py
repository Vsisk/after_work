"""DSL renderer protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.common import GeneratedDSL
from billing_dsl_agent.types.dsl import ValuePlan


class DSLRenderer(Protocol):
    """Render ValuePlan into text-oriented GeneratedDSL."""

    def render(self, plan: ValuePlan) -> GeneratedDSL:
        ...
