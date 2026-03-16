"""Default DSL renderer service."""

from __future__ import annotations

from billing_dsl_agent.types.common import GeneratedDSL, MethodDef
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, MethodPlan, ValuePlan


class DefaultDSLRenderer:
    """Render ValuePlan AST/IR nodes into DSL text."""

    def render(self, plan: ValuePlan) -> GeneratedDSL:
        methods = [MethodDef(name=m.name, body=self._render_expr(m.expr)) for m in plan.methods]
        final_expr_text = self._render_expr(plan.final_expr) if plan.final_expr else ""
        return GeneratedDSL(methods=methods, value_expression=final_expr_text)

    def _render_expr(self, node: ExprNode | None) -> str:
        if node is None:
            return ""

        if node.kind == ExprKind.LITERAL:
            return self._render_literal(node.value)

        if node.kind == ExprKind.CONTEXT_REF:
            return f"$ctx$.{node.value}"

        if node.kind == ExprKind.LOCAL_REF:
            return f"$local$.{node.value}"

        if node.kind == ExprKind.METHOD_REF:
            return str(node.value)

        if node.kind == ExprKind.FIELD_ACCESS:
            base = self._render_expr(node.children[0]) if node.children else ""
            return f"{base}.{node.value}" if base else str(node.value)

        if node.kind == ExprKind.FUNCTION_CALL:
            args = ", ".join(self._render_expr(child) for child in node.children)
            return f"{node.value}({args})"

        if node.kind == ExprKind.QUERY_CALL:
            query_mode = str(node.metadata.get("query_mode", "select"))
            target = str(node.metadata.get("target", ""))
            args = ", ".join(self._render_expr(child) for child in node.children)
            if args:
                return f"{query_mode}({target}, {args})"
            return f"{query_mode}({target})"

        if node.kind == ExprKind.BINARY_OP:
            left = self._render_expr(node.children[0]) if len(node.children) > 0 else ""
            right = self._render_expr(node.children[1]) if len(node.children) > 1 else ""
            op = str(node.value or "+")
            return f"{left} {op} {right}".strip()

        if node.kind == ExprKind.IF_EXPR:
            cond = self._render_expr(node.children[0]) if len(node.children) > 0 else ""
            when_true = self._render_expr(node.children[1]) if len(node.children) > 1 else ""
            when_false = self._render_expr(node.children[2]) if len(node.children) > 2 else ""
            return f"if({cond}, {when_true}, {when_false})"

        if node.kind == ExprKind.LIST_LITERAL:
            items = ", ".join(self._render_expr(child) for child in node.children)
            return f"[{items}]"

        if node.kind == ExprKind.INDEX_ACCESS:
            target = self._render_expr(node.children[0]) if len(node.children) > 0 else ""
            index = self._render_expr(node.children[1]) if len(node.children) > 1 else self._render_literal(node.value)
            return f"{target}[{index}]"

        return str(node.value) if node.value is not None else ""

    @staticmethod
    def _render_literal(value: object) -> str:
        if isinstance(value, str):
            return f'"{value}"'
        if value is True:
            return "true"
        if value is False:
            return "false"
        if value is None:
            return "null"
        return str(value)
