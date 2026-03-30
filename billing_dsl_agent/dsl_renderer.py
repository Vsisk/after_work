from __future__ import annotations

from billing_dsl_agent.models import ExprKind, ExprNode, ProgramNode


class DSLRenderer:
    def render(self, node: ProgramNode | ExprNode) -> str:
        if isinstance(node, ProgramNode):
            lines = [f"def {definition.name} = {self.render_expr(definition.expr)}" for definition in node.definitions]
            lines.append(self.render_expr(node.return_node.expr))
            return "\n".join(lines)
        return self.render_expr(node)

    def render_expr(self, expr: ExprNode) -> str:
        if expr.kind == ExprKind.LITERAL:
            return self._render_literal(expr.value)
        if expr.kind in {ExprKind.CONTEXT_REF, ExprKind.LOCAL_REF, ExprKind.VAR_REF}:
            return str(expr.value)
        if expr.kind == ExprKind.FUNCTION_CALL:
            args = ", ".join(self.render_expr(child) for child in expr.children)
            return f"{expr.value}({args})"
        if expr.kind == ExprKind.BINARY_OP:
            left = self.render_expr(expr.children[0])
            right = self.render_expr(expr.children[1])
            return f"{left} {expr.value} {right}"
        if expr.kind == ExprKind.UNARY_OP:
            operand = self.render_expr(expr.children[0])
            if str(expr.value).isalpha():
                return f"{expr.value} {operand}"
            return f"{expr.value}{operand}"
        if expr.kind == ExprKind.IF_EXPR:
            cond = self.render_expr(expr.children[0])
            yes = self.render_expr(expr.children[1])
            no = self.render_expr(expr.children[2])
            return f"if({cond}, {yes}, {no})"
        if expr.kind == ExprKind.QUERY_CALL:
            mode = str(expr.metadata.get("query_kind") or expr.metadata.get("query_mode") or "select")
            target = str(expr.value)
            target_field = str(expr.metadata.get("target_field") or "").strip()
            if mode in {"fetch", "fetch_one"}:
                rendered_pairs = []
                pair_items = expr.metadata.get("pairs") or []
                if not pair_items:
                    pair_items = [
                        {"key": item.get("field"), "value": item.get("value")}
                        for item in (expr.metadata.get("filters") or [])
                    ]
                for pair in pair_items:
                    key = str(pair.get("key") or "")
                    value = pair.get("value")
                    rendered_value = self.render_expr(value) if isinstance(value, ExprNode) else self._render_literal(value)
                    rendered_pairs.append(f"pair({key}, {rendered_value})")
                return f"{mode}({target}{', ' + ', '.join(rendered_pairs) if rendered_pairs else ''})"

            where_expr = expr.metadata.get("where")
            rendered_where = ""
            if isinstance(where_expr, ExprNode):
                rendered_where = self.render_expr(where_expr)
            elif where_expr is not None:
                rendered_where = self._render_literal(where_expr)

            rendered_filters = []
            for query_filter in expr.metadata.get("filters") or []:
                key = str(query_filter.get("field") or "")
                value = query_filter.get("value")
                rendered_value = self.render_expr(value) if isinstance(value, ExprNode) else self._render_literal(value)
                rendered_filters.append(f"{key}={rendered_value}")

            if rendered_where and rendered_filters:
                rendered_where = f"{rendered_where} and " + " and ".join(rendered_filters)
            elif not rendered_where and rendered_filters:
                rendered_where = " and ".join(rendered_filters)

            target_expr = f"{target}.{target_field}" if target_field else target
            return f"{mode}({target_expr}{', ' + rendered_where if rendered_where else ''})"
        if expr.kind == ExprKind.FIELD_ACCESS:
            return f"{self.render_expr(expr.children[0])}.{expr.value}"
        if expr.kind == ExprKind.LIST_LITERAL:
            return "[" + ", ".join(self.render_expr(child) for child in expr.children) + "]"
        if expr.kind == ExprKind.INDEX_ACCESS:
            return f"{self.render_expr(expr.children[0])}[{self.render_expr(expr.children[1])}]"
        return str(expr.value)

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


def render(node: ProgramNode | ExprNode) -> str:
    return DSLRenderer().render(node)
