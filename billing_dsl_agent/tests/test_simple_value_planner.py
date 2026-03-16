from billing_dsl_agent.services import (
    CodeAgentOrchestrator,
    DefaultDSLRenderer,
    DefaultEnvironmentResolver,
    DefaultExplanationBuilder,
    DefaultResourceMatcher,
    DefaultValidator,
    SimpleRequirementParser,
    SimpleValuePlanner,
)
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, DSLDataType, QueryMode
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.dsl import ExprKind
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import BOBinding, ContextBinding, FunctionBinding, ResolvedEnvironment, ResourceBinding
from billing_dsl_agent.types.request_response import GenerateDSLRequest


def _node_def() -> NodeDef:
    return NodeDef(node_id="n1", node_path="/bill/value", node_name="value", data_type=DSLDataType.STRING)


def test_plan_direct_context_value() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="use context",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT],
        operations=[OperationIntent(op_type="read_context", description="read", expected_inputs=["ctx"])],
    )
    binding = ResourceBinding(
        context_bindings=[
            ContextBinding(var_name="billStatement", scope=ContextScope.GLOBAL, field_name="prepareId")
        ]
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FIELD_ACCESS
    assert plan.final_expr.children[0].kind == ExprKind.CONTEXT_REF


def test_plan_select_one_field_access() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="select_one SYS_BE",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.BO_QUERY],
        operations=[OperationIntent(op_type="query_bo_select_one", description="query", expected_inputs=["bo"])],
    )
    binding = ResourceBinding(
        bo_bindings=[
            BOBinding(
                bo_name="SYS_BE",
                query_mode=QueryMode.SELECT_ONE,
                selected_field_names=["amount"],
            )
        ]
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FIELD_ACCESS
    assert plan.final_expr.children[0].kind == ExprKind.QUERY_CALL
    assert plan.final_expr.children[0].metadata.get("query_mode") == "select_one"


def test_plan_function_wrapped_expression() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="context and function",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT, IntentSourceType.FUNCTION],
        operations=[OperationIntent(op_type="call_function", description="call", expected_inputs=["fn"])],
    )
    binding = ResourceBinding(
        context_bindings=[ContextBinding(var_name="billStatement", scope=ContextScope.GLOBAL)],
        function_bindings=[FunctionBinding(class_name="Common", method_name="Double2Str")],
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.FUNCTION_CALL
    assert plan.final_expr.children[0].kind in {ExprKind.CONTEXT_REF, ExprKind.FIELD_ACCESS}


def test_plan_conditional_expression() -> None:
    planner = SimpleValuePlanner()
    intent = NodeIntent(
        raw_requirement="if context",
        target_node_path="/bill/value",
        target_node_name="value",
        target_data_type=DSLDataType.STRING,
        source_types=[IntentSourceType.CONTEXT, IntentSourceType.CONDITIONAL],
        operations=[OperationIntent(op_type="build_conditional", description="if", expected_inputs=[])],
    )
    binding = ResourceBinding(
        context_bindings=[ContextBinding(var_name="billStatement", scope=ContextScope.GLOBAL)]
    )

    plan = planner.build_plan(intent, binding, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.IF_EXPR
    assert len(plan.final_expr.children) == 3


def test_orchestrator_happy_path_with_simple_planner() -> None:
    orchestrator = CodeAgentOrchestrator(
        parser=SimpleRequirementParser(),
        environment_resolver=DefaultEnvironmentResolver(),
        resource_matcher=DefaultResourceMatcher(),
        value_planner=SimpleValuePlanner(),
        dsl_renderer=DefaultDSLRenderer(),
        validator=DefaultValidator(),
        explanation_builder=DefaultExplanationBuilder(),
    )

    request = GenerateDSLRequest(
        user_requirement="use context billStatement.prepareId and select_one SYS_BE then Common.Double2Str",
        node_def=_node_def(),
        global_context_vars=[
            ContextVarDef(
                name="billStatement",
                scope=ContextScope.GLOBAL,
                fields=[ContextFieldDef(name="prepareId")],
            )
        ],
        available_bos=[BODef(id="bo1", name="SYS_BE")],
        available_functions=[FunctionDef(id="f1", class_name="Common", method_name="Double2Str")],
    )

    response = orchestrator.generate(request)

    assert response.success is True
    assert response.dsl_code.strip() != ""
