from billing_dsl_agent.services.dsl_renderer import DefaultDSLRenderer
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, MethodPlan, ValuePlan


def test_render_method_and_final_expression() -> None:
    renderer = DefaultDSLRenderer()
    plan = ValuePlan(
        target_node_path="/bill/amount",
        methods=[
            MethodPlan(
                name="funcA",
                expr=ExprNode(
                    kind=ExprKind.BINARY_OP,
                    value="+",
                    children=[
                        ExprNode(kind=ExprKind.LITERAL, value=1),
                        ExprNode(kind=ExprKind.LITERAL, value=2),
                    ],
                ),
            )
        ],
        final_expr=ExprNode(
            kind=ExprKind.FUNCTION_CALL,
            value="Common.Double2Str",
            children=[
                ExprNode(kind=ExprKind.METHOD_REF, value="funcA"),
                ExprNode(kind=ExprKind.LITERAL, value=2),
            ],
        ),
    )

    result = renderer.render(plan)

    assert result.methods[0].name == "funcA"
    assert result.methods[0].body == "1 + 2"
    assert result.value_expression == "Common.Double2Str(funcA, 2)"
    assert result.to_text() == "def funcA: 1 + 2\nCommon.Double2Str(funcA, 2)"


def test_renderer_binary_op_and_if_expr() -> None:
    renderer = DefaultDSLRenderer()
    plan = ValuePlan(
        target_node_path="/customer/title",
        final_expr=ExprNode(
            kind=ExprKind.IF_EXPR,
            children=[
                ExprNode(
                    kind=ExprKind.BINARY_OP,
                    value="==",
                    children=[
                        ExprNode(kind=ExprKind.CONTEXT_REF, value="$ctx$.customer.gender"),
                        ExprNode(kind=ExprKind.LITERAL, value="\u7537"),
                    ],
                ),
                ExprNode(kind=ExprKind.LITERAL, value="MR."),
                ExprNode(kind=ExprKind.LITERAL, value="Ms."),
            ],
        ),
    )

    result = renderer.render(plan)

    assert result.value_expression == 'if($ctx$.customer.gender == "\u7537", "MR.", "Ms.")'


def test_render_query_field_access_and_if_expr() -> None:
    renderer = DefaultDSLRenderer()
    query = ExprNode(
        kind=ExprKind.QUERY_CALL,
        metadata={"query_mode": "select_one", "target": "SYS_BE"},
    )
    plan = ValuePlan(
        target_node_path="/bill/region",
        final_expr=ExprNode(
            kind=ExprKind.IF_EXPR,
            children=[
                ExprNode(
                    kind=ExprKind.BINARY_OP,
                    value="!=",
                    children=[
                        ExprNode(kind=ExprKind.FIELD_ACCESS, value="regionId", children=[query]),
                        ExprNode(kind=ExprKind.LITERAL, value=""),
                    ],
                ),
                ExprNode(kind=ExprKind.FIELD_ACCESS, value="regionId", children=[query]),
                ExprNode(kind=ExprKind.LITERAL, value=0),
            ],
        ),
    )

    result = renderer.render(plan)

    assert "select_one(SYS_BE)" in result.value_expression
    assert ".regionId" in result.value_expression
    assert result.value_expression.startswith("if(")
