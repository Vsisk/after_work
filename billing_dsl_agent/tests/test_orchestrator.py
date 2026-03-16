from billing_dsl_agent.services.dsl_renderer import DefaultDSLRenderer
from billing_dsl_agent.services.environment_resolver import DefaultEnvironmentResolver
from billing_dsl_agent.services.explanation_builder import DefaultExplanationBuilder
from billing_dsl_agent.services.orchestrator import CodeAgentOrchestrator
from billing_dsl_agent.services.resource_matcher import DefaultResourceMatcher
from billing_dsl_agent.services.validator import DefaultValidator
from billing_dsl_agent.types.common import DSLDataType
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, MethodPlan, ValuePlan
from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import ResourceBinding, ResolvedEnvironment
from billing_dsl_agent.types.request_response import GenerateDSLRequest


class MockParser:
    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        return NodeIntent(
            raw_requirement=user_requirement,
            target_node_path=node_def.node_path,
            target_node_name=node_def.node_name,
            target_data_type=node_def.data_type,
        )


class MockPlanner:
    def build_plan(self, intent: NodeIntent, binding: ResourceBinding, env: ResolvedEnvironment) -> ValuePlan:
        del intent, binding, env
        return ValuePlan(
            target_node_path="/bill/value",
            methods=[MethodPlan(name="funcA", expr=ExprNode(kind=ExprKind.LITERAL, value=100))],
            final_expr=ExprNode(kind=ExprKind.METHOD_REF, value="funcA"),
        )


def test_orchestrator_happy_path() -> None:
    orchestrator = CodeAgentOrchestrator(
        parser=MockParser(),
        environment_resolver=DefaultEnvironmentResolver(),
        resource_matcher=DefaultResourceMatcher(),
        value_planner=MockPlanner(),
        dsl_renderer=DefaultDSLRenderer(),
        validator=DefaultValidator(),
        explanation_builder=DefaultExplanationBuilder(),
    )

    request = GenerateDSLRequest(
        user_requirement="生成账单金额节点",
        node_def=NodeDef(
            node_id="node-1",
            node_path="/bill/value",
            node_name="value",
            data_type=DSLDataType.MONEY,
        ),
    )

    response = orchestrator.generate(request)

    assert response.success is True
    assert response.dsl_code == "def funcA: 100\nfuncA"
    assert response.validation_result is not None and response.validation_result.is_valid is True
    assert response.explanation is not None
