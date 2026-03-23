from __future__ import annotations

from billing_dsl_agent.models import ExprKind, ExprNode


class EDSLRenderer:
    def render(self, expr: ExprNode) -> str:
        if expr.kind == ExprKind.LITERAL:
            return self._render_literal(expr.value)
        if expr.kind == ExprKind.CONTEXT_REF:
            return str(expr.value)
        if expr.kind == ExprKind.LOCAL_REF:
            return str(expr.value)
        if expr.kind == ExprKind.FUNCTION_CALL:
            args = ", ".join(self.render(child) for child in expr.children)
            return f"{expr.value}({args})"
        if expr.kind == ExprKind.BINARY_OP:
            left = self.render(expr.children[0])
            right = self.render(expr.children[1])
            return f"{left} {expr.value} {right}"
        if expr.kind == ExprKind.IF_EXPR:
            cond = self.render(expr.children[0])
            yes = self.render(expr.children[1])
            no = self.render(expr.children[2])
            return f"if({cond}, {yes}, {no})"
        if expr.kind == ExprKind.QUERY_CALL:
            mode = str(expr.metadata.get("query_mode") or "select")
            target = str(expr.value)
            target_field = str(expr.metadata.get("target_field") or "").strip()
            params = expr.metadata.get("params") or []
            rendered_params = []
            for param in params:
                key = str(param.get("param_name") or "")
                val = param.get("value")
                source = str(param.get("value_source_type") or "")
                if source == "constant":
                    rendered_val = self._render_literal(val)
                else:
                    rendered_val = str(val)
                rendered_params.append(f"{key}={rendered_val}")
            param_text = ", ".join(rendered_params)
            if target_field:
                return f"{mode}({target}.{target_field}{', ' + param_text if param_text else ''})"
            return f"{mode}({target}{', ' + param_text if param_text else ''})"
        if expr.kind == ExprKind.FIELD_ACCESS:
            return f"{self.render(expr.children[0])}.{expr.value}"
        if expr.kind == ExprKind.LIST_LITERAL:
            return "[" + ", ".join(self.render(child) for child in expr.children) + "]"
        if expr.kind == ExprKind.INDEX_ACCESS:
            return f"{self.render(expr.children[0])}[{self.render(expr.children[1])}]"
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


class DSLRenderer(EDSLRenderer):
    pass


def render(expr: ExprNode) -> str:
    return EDSLRenderer().render(expr)
