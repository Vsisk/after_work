"""Simple AST value planner for LLM-first DSL generation."""

from __future__ import annotations

from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, ValuePlan
from billing_dsl_agent.types.plan import ResolvedEnvironment


class SimpleValuePlanner:
    """Build runnable ValuePlan AST from an explicit plan draft."""

    def build_plan(self, plan_draft: PlanDraft, env: ResolvedEnvironment) -> ValuePlan:
        del env
        base_expr = self._build_base_expr(plan_draft)
        wrapped_expr = self._wrap_function_if_needed(base_expr, plan_draft)
        final_expr = self._wrap_conditional_if_needed(wrapped_expr, plan_draft)
        return ValuePlan(
            target_node_path=str(plan_draft.raw_plan.get("target_node_path", "")),
            methods=[],
            final_expr=final_expr or ExprNode(kind=ExprKind.LITERAL, value=""),
        )

    def _build_base_expr(self, plan_draft: PlanDraft) -> ExprNode:
        query_expr = self._build_query_expr(plan_draft)
        if query_expr is not None:
            return query_expr
        if plan_draft.context_refs:
            return self._build_ref_expr_from_path(plan_draft.context_refs[0])
        literal_value = plan_draft.semantic_slots.get("literal")
        if literal_value is not None:
            return ExprNode(kind=ExprKind.LITERAL, value=literal_value)
        return ExprNode(kind=ExprKind.LITERAL, value="")

    def _build_query_expr(self, plan_draft: PlanDraft) -> ExprNode | None:
        if not plan_draft.bo_refs:
            return None

        bo_ref = dict(plan_draft.bo_refs[0])
        target = str(bo_ref.get("bo_name") or bo_ref.get("name") or "").strip()
        query_mode = str(bo_ref.get("query_mode") or "select").lower()
        query_expr = ExprNode(
            kind=ExprKind.QUERY_CALL,
            metadata={"query_mode": query_mode, "target": target},
            children=[],
        )

        field_name = str(bo_ref.get("field") or bo_ref.get("target_field") or "").strip()
        if not field_name:
            selected = bo_ref.get("selected_field_names") or []
            if selected:
                field_name = str(selected[0]).strip()

        if field_name:
            return ExprNode(kind=ExprKind.FIELD_ACCESS, value=field_name, children=[query_expr])
        return query_expr

    def _wrap_function_if_needed(self, base_expr: ExprNode, plan_draft: PlanDraft) -> ExprNode:
        if not plan_draft.function_refs:
            return base_expr
        args: list[ExprNode] = [base_expr]
        for raw_arg in plan_draft.semantic_slots.get("function_args") or []:
            arg = self._coerce_value_to_expr(raw_arg)
            if arg is not None:
                args.append(arg)
        return ExprNode(kind=ExprKind.FUNCTION_CALL, value=plan_draft.function_refs[0], children=args)

    def _wrap_conditional_if_needed(self, expr: ExprNode, plan_draft: PlanDraft) -> ExprNode:
        pattern = str(plan_draft.expression_pattern or "").lower()
        slots = plan_draft.semantic_slots or {}
        if "if(" not in pattern and "conditional_mapping" not in slots and "true_output" not in slots:
            return expr

        condition_ref = str(slots.get("condition_ref") or "").strip()
        if not condition_ref and plan_draft.context_refs:
            condition_ref = plan_draft.context_refs[0]
        if not condition_ref:
            return expr

        cond_expr = ExprNode(
            kind=ExprKind.BINARY_OP,
            value=str(slots.get("condition_operator") or "=="),
            children=[
                self._build_ref_expr_from_path(condition_ref),
                ExprNode(kind=ExprKind.LITERAL, value=slots.get("condition_value")),
            ],
        )
        true_expr = self._coerce_value_to_expr(slots.get("true_output")) or expr
        false_expr = self._coerce_value_to_expr(slots.get("false_output")) or ExprNode(kind=ExprKind.LITERAL, value="")
        return ExprNode(kind=ExprKind.IF_EXPR, children=[cond_expr, true_expr, false_expr])

    @staticmethod
    def _build_ref_expr_from_path(path: str) -> ExprNode:
        text = str(path).strip()
        if text.startswith("$local$."):
            return ExprNode(kind=ExprKind.LOCAL_REF, value=text)
        return ExprNode(kind=ExprKind.CONTEXT_REF, value=text)

    @staticmethod
    def _coerce_value_to_expr(value: object) -> ExprNode | None:
        if value is None:
            return None
        if isinstance(value, ExprNode):
            return value
        text = str(value).strip() if isinstance(value, str) else value
        if isinstance(text, str) and text.startswith(("$ctx$.", "$local$.")):
            return SimpleValuePlanner._build_ref_expr_from_path(text)
        return ExprNode(kind=ExprKind.LITERAL, value=value)
