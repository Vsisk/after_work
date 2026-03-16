"""Simple AST value planner for MVP DSL generation chain."""

from __future__ import annotations

from billing_dsl_agent.types.dsl import ExprKind, ExprNode, MethodPlan, ValuePlan
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.plan import ResolvedEnvironment, ResourceBinding


class SimpleValuePlanner:
    """Build minimal ValuePlan using intent keywords and matched resources."""

    def build_plan(self, intent: NodeIntent, binding: ResourceBinding, env: ResolvedEnvironment) -> ValuePlan:
        del env  # reserved for future semantic planning

        final_expr = self._build_base_expr(intent, binding)

        if IntentSourceType.FUNCTION in intent.source_types and binding.function_bindings:
            fn = binding.function_bindings[0]
            final_expr = ExprNode(
                kind=ExprKind.FUNCTION_CALL,
                value=f"{fn.class_name}.{fn.method_name}" if fn.class_name else fn.method_name,
                children=[final_expr],
            )

        if any(op.op_type == "if" for op in intent.operations):
            cond = ExprNode(kind=ExprKind.LITERAL, value=True)
            final_expr = ExprNode(
                kind=ExprKind.IF_EXPR,
                children=[
                    cond,
                    final_expr,
                    ExprNode(kind=ExprKind.LITERAL, value=""),
                ],
            )

        return ValuePlan(target_node_path=intent.target_node_path, methods=[], final_expr=final_expr)

    def _build_base_expr(self, intent: NodeIntent, binding: ResourceBinding) -> ExprNode:
        if binding.bo_bindings:
            bo = binding.bo_bindings[0]
            mode = bo.query_mode.value.lower()
            query_expr = ExprNode(
                kind=ExprKind.QUERY_CALL,
                metadata={
                    "query_mode": mode,
                    "target": bo.naming_sql_name or bo.bo_name,
                },
                children=[ExprNode(kind=ExprKind.LITERAL, value=True)],
            )
            if bo.selected_field_names:
                return ExprNode(kind=ExprKind.FIELD_ACCESS, value=bo.selected_field_names[0], children=[query_expr])
            if mode in {"select_one", "fetch_one"}:
                return ExprNode(kind=ExprKind.FIELD_ACCESS, value="id", children=[query_expr])
            return query_expr

        global_ctx = next((c for c in binding.context_bindings if c.scope.value == "GLOBAL"), None)
        local_ctx = next((c for c in binding.context_bindings if c.scope.value == "LOCAL"), None)

        if global_ctx:
            base = ExprNode(kind=ExprKind.CONTEXT_REF, value=global_ctx.var_name)
            if global_ctx.field_name:
                return ExprNode(kind=ExprKind.FIELD_ACCESS, value=global_ctx.field_name, children=[base])
            return base

        if local_ctx:
            base = ExprNode(kind=ExprKind.LOCAL_REF, value=local_ctx.var_name)
            if local_ctx.field_name:
                return ExprNode(kind=ExprKind.FIELD_ACCESS, value=local_ctx.field_name, children=[base])
            return base

        if IntentSourceType.CONTEXT in intent.source_types:
            return ExprNode(kind=ExprKind.CONTEXT_REF, value="fallbackContext")
        if IntentSourceType.LOCAL_CONTEXT in intent.source_types:
            return ExprNode(kind=ExprKind.LOCAL_REF, value="fallbackLocal")

        return ExprNode(kind=ExprKind.LITERAL, value="")
