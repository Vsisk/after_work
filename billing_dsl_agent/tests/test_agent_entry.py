from billing_dsl_agent.agent_entry import ExpressionAgent
from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import GenerateExpressionRequest
from billing_dsl_agent.plan_validator import PlanValidator
from billing_dsl_agent.schema_provider import SchemaProvider


def test_generate_expression_happy_path() -> None:
    plan = {
        "intent_summary": "direct",
        "expression_pattern": "direct_ref",
        "context_refs": ["$ctx$.customer.id"],
    }
    planner = LLMPlanner(StubOpenAIClient(plan_response=plan))
    agent = ExpressionAgent(
        schema_provider=SchemaProvider(),
        llm_planner=planner,
        plan_validator=PlanValidator(planner=None),
    )

    request = GenerateExpressionRequest(
        node_info={"node_path": "invoice.customer.id", "node_name": "id"},
        user_query="返回客户ID",
        site_id="site_a",
        project_id="project_a",
    )
    response = agent.generate_expression(request)

    assert response.success is True
    assert response.edsl_expression


def test_generate_expression_validation_failure() -> None:
    bad_plan = {
        "intent_summary": "bad",
        "expression_pattern": "direct_ref",
        "context_refs": ["$ctx$.invalid.path"],
    }
    planner = LLMPlanner(StubOpenAIClient(plan_response=bad_plan))
    agent = ExpressionAgent(
        schema_provider=SchemaProvider(),
        llm_planner=planner,
        plan_validator=PlanValidator(planner=None),
    )

    request = GenerateExpressionRequest(
        node_info={"node_path": "invoice.customer.title", "node_name": "title"},
        user_query="生成称谓",
        site_id="site_a",
        project_id="project_a",
    )
    response = agent.generate_expression(request)

    assert response.success is False
    assert response.failure_reason == "plan validation failed"
