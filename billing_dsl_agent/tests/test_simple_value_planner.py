from billing_dsl_agent.services.simple_value_planner import SimpleValuePlanner
from billing_dsl_agent.types.common import ContextScope, DSLDataType, QueryMode
from billing_dsl_agent.types.dsl import ExprKind
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import BOBinding, ContextBinding, FunctionBinding, ResolvedEnvironment, ResourceBinding


def _node_def() -> NodeDef:
    return NodeDef(node_id="n1", node_path="/bill/value", node_name="value", data_type=DSLDataType.STRING)


def test_plan_direct_context_expr() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="\u53d6 prepareId",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT],
        semantic_slots={"context_field_hints": ["prepareId"]},
    )
    binding = ResourceBinding(
        context_bindings=[ContextBinding(var_name="billStatement", scope=ContextScope.GLOBAL, field_name="prepareId")]
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.CONTEXT_REF
    assert plan.final_expr.value == "$ctx$.billStatement.prepareId"


def test_plan_select_one_field_expr() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="select_one BB_PREP_SUB",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.BO_QUERY],
        semantic_slots={"bo_name": "BB_PREP_SUB", "query_mode": "select_one", "target_field": "regionId"},
    )
    binding = ResourceBinding(
        bo_bindings=[
            BOBinding(
                bo_name="BB_PREP_SUB",
                query_mode=QueryMode.SELECT_ONE,
                selected_field_names=["regionId"],
            )
        ]
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FIELD_ACCESS
    assert plan.final_expr.value == "regionId"
    assert plan.final_expr.children[0].kind == ExprKind.QUERY_CALL
    assert plan.final_expr.children[0].metadata["query_mode"] == "select_one"
    assert plan.final_expr.children[0].metadata["target"] == "BB_PREP_SUB"


def test_plan_function_wrap_expr() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="\u5c06\u91d1\u989d\u683c\u5f0f\u5316",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT, IntentSourceType.FUNCTION],
        semantic_slots={"function_name": "Common.Double2Str", "format_precision": 2},
    )
    binding = ResourceBinding(
        context_bindings=[ContextBinding(var_name="billStatement", scope=ContextScope.GLOBAL, field_name="amount")],
        function_bindings=[FunctionBinding(class_name="Common", method_name="Double2Str")],
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FUNCTION_CALL
    assert plan.final_expr.value == "Common.Double2Str"
    assert plan.final_expr.children[0].kind == ExprKind.CONTEXT_REF
    assert plan.final_expr.children[0].value == "$ctx$.billStatement.amount"
    assert plan.final_expr.children[1].kind == ExprKind.LITERAL
    assert plan.final_expr.children[1].value == 2


def test_plan_if_expr() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="\u5982\u679c\u8d26\u671f\u4e3a0\u5219\u8fd4\u56deA\uff0c\u5426\u5219\u8fd4\u56deB",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT, IntentSourceType.CONDITIONAL],
        semantic_slots={
            "condition_field_hint": "\u8d26\u671f",
            "condition_operator": "==",
            "condition_value": "0",
            "true_output": "A",
            "false_output": "B",
        },
    )
    binding = ResourceBinding(
        context_bindings=[ContextBinding(var_name="billStatement", scope=ContextScope.GLOBAL, field_name="billCycleId")],
        semantic_bindings={"condition_field": "$ctx$.billStatement.billCycleId"},
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.IF_EXPR
    assert len(plan.final_expr.children) == 3
    assert plan.final_expr.children[0].kind == ExprKind.BINARY_OP
    assert plan.final_expr.children[0].value == "=="
    assert plan.final_expr.children[1].kind == ExprKind.LITERAL
    assert plan.final_expr.children[1].value == "A"
    assert plan.final_expr.children[2].kind == ExprKind.LITERAL
    assert plan.final_expr.children[2].value == "B"


def test_plan_conditional_mapping_expr() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u7537\u65f6\uff0c\u663e\u793aMR.\uff0c\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u5973\u65f6\uff0c\u663e\u793aMs.",
        target_node_path="/customer/title",
        target_node_name="title",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT, IntentSourceType.CONDITIONAL],
        semantic_slots={
            "conditional_mapping": True,
            "condition_field_hint": "\u5ba2\u6237\u6027\u522b",
            "condition_operator": "==",
            "condition_value": "\u7537",
            "true_output": "MR.",
            "false_output": "Ms.",
        },
    )
    binding = ResourceBinding(
        context_bindings=[ContextBinding(var_name="customer", scope=ContextScope.GLOBAL, field_name="gender")],
        semantic_bindings={"condition_field": "$ctx$.customer.gender"},
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.IF_EXPR
    cond_expr, true_expr, false_expr = plan.final_expr.children
    assert cond_expr.kind == ExprKind.BINARY_OP
    assert cond_expr.children[0].kind == ExprKind.CONTEXT_REF
    assert cond_expr.children[0].value == "$ctx$.customer.gender"
    assert cond_expr.children[1].kind == ExprKind.LITERAL
    assert cond_expr.children[1].value == "\u7537"
    assert true_expr.value == "MR."
    assert false_expr.value == "Ms."
