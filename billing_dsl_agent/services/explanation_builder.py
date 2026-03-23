"""Default explanation builder service."""

from __future__ import annotations

from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.common import StructuredExplanation
from billing_dsl_agent.types.dsl import ValuePlan


class DefaultExplanationBuilder:
    """Build minimal structured explanation from orchestration artifacts."""

    def build(
        self,
        plan_draft: PlanDraft,
        plan: ValuePlan,
    ) -> StructuredExplanation:
        method_summaries = [f"method {method.name} defined" for method in plan.methods]
        final_summary = "final expression planned" if plan.final_expr else "final expression missing"
        return StructuredExplanation(
            intent_summary=plan_draft.intent_summary,
            used_context_vars=[ref for ref in plan_draft.context_refs if ref.startswith("$ctx$.")],
            used_local_vars=[ref for ref in plan_draft.context_refs if ref.startswith("$local$.")],
            used_bos=[str(item.get("bo_name") or item.get("name") or "") for item in plan_draft.bo_refs],
            used_naming_sqls=[],
            used_functions=list(plan_draft.function_refs),
            method_summaries=method_summaries,
            final_expression_summary=final_summary,
        )
