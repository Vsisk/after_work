from __future__ import annotations

from billing_dsl_agent.models import (
    BinaryOpPlanNode,
    ContextRefPlanNode,
    ExprKind,
    ExprNode,
    FieldAccessPlanNode,
    FilteredEnvironment,
    FunctionCallPlanNode,
    IfPlanNode,
    IndexAccessPlanNode,
    ListLiteralPlanNode,
    LiteralPlanNode,
    LocalRefPlanNode,
    ProgramNode,
    ProgramPlan,
    QueryCallPlanNode,
    ReturnNode,
    UnaryOpPlanNode,
    VarRefPlanNode,
    VariableDefNode,
)


class ASTBuilder:
    def build_program_from_plan(self, plan: ProgramPlan, env: FilteredEnvironment) -> ProgramNode:
        definitions = [
            VariableDefNode(
                name=definition.name,
                expr=self.build_expr_from_plan(definition.expr, env),
            )
            for definition in plan.definitions
            if definition.kind == "variable"
        ]
        return ProgramNode(
            definitions=definitions,
            return_node=ReturnNode(expr=self.build_expr_from_plan(plan.return_expr, env)),
        )

    def build_expr_from_plan(self, node, env: FilteredEnvironment) -> ExprNode:
        registry = env.registry

        if isinstance(node, LiteralPlanNode):
            return ExprNode(kind=ExprKind.LITERAL, value=node.value)

        if isinstance(node, ContextRefPlanNode):
            return ExprNode(kind=ExprKind.CONTEXT_REF, value=node.path)

        if isinstance(node, LocalRefPlanNode):
            return ExprNode(kind=ExprKind.LOCAL_REF, value=node.path)

        if isinstance(node, VarRefPlanNode):
            return ExprNode(kind=ExprKind.VAR_REF, value=node.name)

        if isinstance(node, FunctionCallPlanNode):
            function_name = node.function_name or node.function_id or ""
            if node.function_id and node.function_id in registry.functions:
                function_name = registry.functions[node.function_id].full_name
            return ExprNode(
                kind=ExprKind.FUNCTION_CALL,
                value=function_name,
                children=[self.build_expr_from_plan(argument, env) for argument in node.args],
                metadata={"function_id": node.function_id},
            )

        if isinstance(node, QueryCallPlanNode):
            source_name = node.source_name
            if node.bo_id and node.bo_id in registry.bos:
                source_name = registry.bos[node.bo_id].bo_name
            return ExprNode(
                kind=ExprKind.QUERY_CALL,
                value=source_name,
                metadata={
                    "query_kind": node.query_kind,
                    "target_field": node.field,
                    "bo_id": node.bo_id,
                    "data_source": node.data_source,
                    "naming_sql_id": node.naming_sql_id,
                    "filters": [
                        {
                            "field": query_filter.field,
                            "value": self.build_expr_from_plan(query_filter.value, env),
                        }
                        for query_filter in node.filters
                    ],
                },
            )

        if isinstance(node, IfPlanNode):
            return ExprNode(
                kind=ExprKind.IF_EXPR,
                children=[
                    self.build_expr_from_plan(node.condition, env),
                    self.build_expr_from_plan(node.then_expr, env),
                    self.build_expr_from_plan(node.else_expr, env),
                ],
            )

        if isinstance(node, BinaryOpPlanNode):
            return ExprNode(
                kind=ExprKind.BINARY_OP,
                value=node.operator,
                children=[
                    self.build_expr_from_plan(node.left, env),
                    self.build_expr_from_plan(node.right, env),
                ],
            )

        if isinstance(node, UnaryOpPlanNode):
            return ExprNode(
                kind=ExprKind.UNARY_OP,
                value=node.operator,
                children=[self.build_expr_from_plan(node.operand, env)],
            )

        if isinstance(node, FieldAccessPlanNode):
            return ExprNode(
                kind=ExprKind.FIELD_ACCESS,
                value=node.field,
                children=[self.build_expr_from_plan(node.base, env)],
            )

        if isinstance(node, IndexAccessPlanNode):
            return ExprNode(
                kind=ExprKind.INDEX_ACCESS,
                children=[
                    self.build_expr_from_plan(node.base, env),
                    self.build_expr_from_plan(node.index, env),
                ],
            )

        if isinstance(node, ListLiteralPlanNode):
            return ExprNode(
                kind=ExprKind.LIST_LITERAL,
                children=[self.build_expr_from_plan(item, env) for item in node.items],
            )

        raise TypeError(f"unsupported expr node: {type(node).__name__}")

    def build_ast(self, plan: ProgramPlan, env: FilteredEnvironment) -> ProgramNode:
        return self.build_program_from_plan(plan, env)


def build_ast(plan: ProgramPlan, env: FilteredEnvironment) -> ProgramNode:
    return ASTBuilder().build_program_from_plan(plan, env)
