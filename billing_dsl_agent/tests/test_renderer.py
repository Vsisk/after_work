from billing_dsl_agent.services.dsl_renderer import DefaultDSLRenderer
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, MethodPlan, ValuePlan


def test_render_method_and_final_expression() -> None:
    renderer = DefaultDSLRenderer()
    plan = ValuePlan(
        target_node_path="/bill/amount",
        methods=[
            MethodPlan(
                name="funcA",
                expr=ExprNode(kind=ExprKind.BINARY_OP, value="+", children=[
                    ExprNode(kind=ExprKind.LITERAL, value=1),
                    ExprNode(kind=ExprKind.LITERAL, value=2),
                ]),
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
