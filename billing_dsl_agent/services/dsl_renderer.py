"""Default DSL renderer service."""

from __future__ import annotations

from billing_dsl_agent.types.common import GeneratedDSL, MethodDef
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, ValuePlan


class DefaultDSLRenderer:
    """Render ValuePlan AST/IR nodes into DSL text."""

    def render(self, plan: ValuePlan) -> GeneratedDSL:
        methods = [MethodDef(name=method.name, body=self._render_expr(method.expr)) for method in plan.methods]
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
            parent = self._render_expr(node.children[0]) if node.children else ""
            return f"{parent}.{node.value}" if parent else str(node.value)

        if node.kind == ExprKind.FUNCTION_CALL:
            args = self._render_args(node.children)
            return f"{node.value}({args})"

        if node.kind == ExprKind.QUERY_CALL:
            query_mode = self._normalize_query_mode(node.metadata.get("query_mode", "select"))
            target = str(node.metadata.get("target", ""))
            args = self._render_args(node.children)
            return f"{query_mode}({target}, {args})" if args else f"{query_mode}({target})"

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
            return f"[{self._render_args(node.children)}]"

        if node.kind == ExprKind.INDEX_ACCESS:
            obj = self._render_expr(node.children[0]) if len(node.children) > 0 else ""
            index = self._render_expr(node.children[1]) if len(node.children) > 1 else self._render_literal(node.value)
            return f"{obj}[{index}]"

        return str(node.value) if node.value is not None else ""

    def _render_args(self, children: list[ExprNode]) -> str:
        return ", ".join(self._render_expr(child) for child in children)

    @staticmethod
    def _normalize_query_mode(value: object) -> str:
        raw = str(value or "select").lower()
        supported = {"select", "select_one", "fetch", "fetch_one"}
        return raw if raw in supported else "select"

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
