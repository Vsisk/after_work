"""Default explanation builder service."""

from __future__ import annotations

from billing_dsl_agent.types.common import StructuredExplanation
from billing_dsl_agent.types.dsl import ValuePlan
from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.plan import ResourceBinding


class DefaultExplanationBuilder:
    """Build minimal structured explanation from orchestration artifacts."""

    def build(
        self,
        intent: NodeIntent,
        binding: ResourceBinding,
        plan: ValuePlan,
    ) -> StructuredExplanation:
        method_summaries = [f"method {method.name} defined" for method in plan.methods]
        final_summary = "final expression planned" if plan.final_expr else "final expression missing"
        return StructuredExplanation(
            intent_summary=f"Generate DSL for node {intent.target_node_path}",
            used_context_vars=[b.var_name for b in binding.context_bindings if b.scope.value == "GLOBAL"],
            used_local_vars=[b.var_name for b in binding.context_bindings if b.scope.value == "LOCAL"],
            used_bos=[b.bo_name for b in binding.bo_bindings],
            used_naming_sqls=[b.naming_sql_name for b in binding.bo_bindings if b.naming_sql_name],
            used_functions=[f"{b.class_name}.{b.method_name}" if b.class_name else b.method_name for b in binding.function_bindings],
            method_summaries=method_summaries,
            final_expression_summary=final_summary,
        )
