"""Value planner protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.dsl import ValuePlan
from billing_dsl_agent.types.plan import ResolvedEnvironment


class ValuePlanner(Protocol):
    """Build AST/IR value plan for final DSL rendering."""

    def build_plan(self, plan_draft: PlanDraft, env: ResolvedEnvironment) -> ValuePlan:
        ...
