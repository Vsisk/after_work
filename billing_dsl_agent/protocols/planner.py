"""Value planner protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.dsl import ValuePlan
from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.plan import ResolvedEnvironment, ResourceBinding


class ValuePlanner(Protocol):
    """Build AST/IR value plan for final DSL rendering."""

    def build_plan(self, intent: NodeIntent, binding: ResourceBinding, env: ResolvedEnvironment) -> ValuePlan:
        ...
