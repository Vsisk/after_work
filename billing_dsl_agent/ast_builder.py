from __future__ import annotations

from billing_dsl_agent.models import ExprKind, ExprNode, PlanDraft


class ASTBuilder:
    def build(self, plan: PlanDraft) -> ExprNode:
        pattern = plan.expression_pattern
        if pattern == "if":
            cond_ref = str(plan.semantic_slots.get("condition_ref") or plan.context_refs[0])
            cond = ExprNode(
                kind=ExprKind.BINARY_OP,
                value=str(plan.semantic_slots.get("condition_operator") or "=="),
                children=[
                    ExprNode(kind=ExprKind.CONTEXT_REF, value=cond_ref),
                    ExprNode(kind=ExprKind.LITERAL, value=plan.semantic_slots.get("condition_value")),
                ],
            )
            return ExprNode(
                kind=ExprKind.IF_EXPR,
                children=[
                    cond,
                    ExprNode(kind=ExprKind.LITERAL, value=plan.semantic_slots.get("true_output")),
                    ExprNode(kind=ExprKind.LITERAL, value=plan.semantic_slots.get("false_output")),
                ],
            )

        if pattern in {"select", "select_one", "fetch", "fetch_one"} and plan.bo_refs:
            bo_ref = plan.bo_refs[0]
            return ExprNode(
                kind=ExprKind.QUERY_CALL,
                value=bo_ref.get("bo_name"),
                metadata={
                    "query_mode": pattern,
                    "target_field": bo_ref.get("field") or bo_ref.get("target_field") or "",
                    "params": list(bo_ref.get("params") or []),
                },
            )

        if pattern == "function_call" and plan.function_refs:
            args: list[ExprNode] = []
            for value in plan.semantic_slots.get("function_args", []):
                if isinstance(value, str) and value.startswith("$ctx$."):
                    args.append(ExprNode(kind=ExprKind.CONTEXT_REF, value=value))
                else:
                    args.append(ExprNode(kind=ExprKind.LITERAL, value=value))
            return ExprNode(kind=ExprKind.FUNCTION_CALL, value=plan.function_refs[0], children=args)

        if plan.context_refs:
            return ExprNode(kind=ExprKind.CONTEXT_REF, value=plan.context_refs[0])

        return ExprNode(kind=ExprKind.LITERAL, value=plan.semantic_slots.get("literal"))

    def build_ast(self, plan: PlanDraft) -> ExprNode:
        return self.build(plan)


def build_ast(plan: PlanDraft) -> ExprNode:
    return ASTBuilder().build(plan)
