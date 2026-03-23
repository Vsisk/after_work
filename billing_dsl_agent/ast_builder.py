from __future__ import annotations

from billing_dsl_agent.models import ExprKind, ExprNode, FilteredEnvironment, PlanDraft


class ASTBuilder:
    def build_ast(self, plan: PlanDraft, env: FilteredEnvironment) -> ExprNode:
        pattern = plan.expression_pattern
        registry = env.registry

        def context_path(context_id: str) -> str:
            return registry.contexts[context_id].path

        if pattern == "if":
            cond_ref_id = str(plan.semantic_slots.get("condition_ref") or plan.context_refs[0])
            cond = ExprNode(
                kind=ExprKind.BINARY_OP,
                value=str(plan.semantic_slots.get("condition_operator") or "=="),
                children=[
                    ExprNode(kind=ExprKind.CONTEXT_REF, value=context_path(cond_ref_id)),
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
            bo = registry.bos[str(bo_ref.get("bo_id") or "")]
            field_id = str(bo_ref.get("field_id") or "")
            target_field = field_id.split(":")[-1] if field_id else ""
            return ExprNode(
                kind=ExprKind.QUERY_CALL,
                value=bo.bo_name,
                metadata={
                    "query_mode": pattern,
                    "target_field": target_field,
                    "params": list(bo_ref.get("params") or []),
                },
            )

        if pattern == "function_call" and plan.function_refs:
            function = registry.functions[plan.function_refs[0]]
            args: list[ExprNode] = []
            for value in plan.semantic_slots.get("function_args", []):
                if isinstance(value, str) and value in registry.contexts:
                    args.append(ExprNode(kind=ExprKind.CONTEXT_REF, value=context_path(value)))
                elif isinstance(value, str) and value.startswith("$ctx$."):
                    args.append(ExprNode(kind=ExprKind.CONTEXT_REF, value=value))
                else:
                    args.append(ExprNode(kind=ExprKind.LITERAL, value=value))
            return ExprNode(kind=ExprKind.FUNCTION_CALL, value=function.full_name, children=args)

        if plan.context_refs:
            return ExprNode(kind=ExprKind.CONTEXT_REF, value=context_path(plan.context_refs[0]))

        return ExprNode(kind=ExprKind.LITERAL, value=plan.semantic_slots.get("literal"))


def build_ast(plan: PlanDraft, env: FilteredEnvironment) -> ExprNode:
    return ASTBuilder().build_ast(plan, env)
