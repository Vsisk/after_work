from billing_dsl_agent.services.simple_value_planner import SimpleValuePlanner
from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.dsl import ExprKind
from billing_dsl_agent.types.plan import ResolvedEnvironment


def test_plan_direct_context_expr() -> None:
    planner = SimpleValuePlanner()
    draft = PlanDraft(
        intent_summary="direct context",
        context_refs=["$ctx$.billStatement.prepareId"],
        expression_pattern="direct_ref",
    )

    plan = planner.build_plan(draft, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.CONTEXT_REF
    assert plan.final_expr.value == "$ctx$.billStatement.prepareId"


def test_plan_select_one_field_expr() -> None:
    planner = SimpleValuePlanner()
    draft = PlanDraft(
        intent_summary="query field",
        bo_refs=[{"bo_name": "BB_PREP_SUB", "query_mode": "select_one", "field": "regionId"}],
        expression_pattern="query(field)",
    )

    plan = planner.build_plan(draft, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FIELD_ACCESS
    assert plan.final_expr.value == "regionId"
    assert plan.final_expr.children[0].kind == ExprKind.QUERY_CALL
    assert plan.final_expr.children[0].metadata["query_mode"] == "select_one"
    assert plan.final_expr.children[0].metadata["target"] == "BB_PREP_SUB"


def test_plan_function_wrap_expr() -> None:
    planner = SimpleValuePlanner()
    draft = PlanDraft(
        intent_summary="function wrap",
        context_refs=["$ctx$.billStatement.amount"],
        function_refs=["Common.Double2Str"],
        semantic_slots={"function_args": [2]},
        expression_pattern="function_call(value)",
    )

    plan = planner.build_plan(draft, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FUNCTION_CALL
    assert plan.final_expr.value == "Common.Double2Str"
    assert plan.final_expr.children[0].kind == ExprKind.CONTEXT_REF
    assert plan.final_expr.children[0].value == "$ctx$.billStatement.amount"
    assert plan.final_expr.children[1].kind == ExprKind.LITERAL
    assert plan.final_expr.children[1].value == 2


def test_plan_conditional_mapping_expr() -> None:
    planner = SimpleValuePlanner()
    draft = PlanDraft(
        intent_summary="conditional mapping",
        context_refs=["$ctx$.customer.gender"],
        semantic_slots={
            "condition_ref": "$ctx$.customer.gender",
            "condition_operator": "==",
            "condition_value": "男",
            "true_output": "MR.",
            "false_output": "Ms.",
        },
        expression_pattern="if(condition, true, false)",
    )

    plan = planner.build_plan(draft, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.IF_EXPR
    cond_expr, true_expr, false_expr = plan.final_expr.children
    assert cond_expr.kind == ExprKind.BINARY_OP
    assert cond_expr.children[0].kind == ExprKind.CONTEXT_REF
    assert cond_expr.children[0].value == "$ctx$.customer.gender"
    assert cond_expr.children[1].kind == ExprKind.LITERAL
    assert cond_expr.children[1].value == "男"
    assert true_expr.value == "MR."
    assert false_expr.value == "Ms."
