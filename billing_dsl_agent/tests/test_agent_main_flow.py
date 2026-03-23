from billing_dsl_agent.agent_entry import DSLAgent
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.llm_planner import LLMPlanner, StubOpenAIClient
from billing_dsl_agent.models import GenerateDSLRequest, NodeDef
from billing_dsl_agent.plan_validator import PlanValidator


def _base_request() -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement="生成账单字段",
        node_def=NodeDef(node_id="n1", node_path="invoice.customer.title", node_name="title", data_type="string"),
        context_schema={"customer": {"gender": "string", "id": "string"}},
        bo_schema={"CustomerBO": ["id", "name", "gender"]},
        function_schema=["str.upper", "format.title"],
    )


def test_if_expr() -> None:
    plan = {
        "intent_summary": "if by gender",
        "expression_pattern": "if",
        "context_refs": ["$ctx$.customer.gender"],
        "semantic_slots": {
            "condition_ref": "$ctx$.customer.gender",
            "condition_operator": "==",
            "condition_value": "男",
            "true_output": "MR.",
            "false_output": "Ms.",
        },
    }
    agent = DSLAgent(llm_planner=LLMPlanner(StubOpenAIClient(plan_response=plan)))
    response = agent.generate_dsl(_base_request())
    assert response.success is True
    assert response.dsl == 'if($ctx$.customer.gender == "男", "MR.", "Ms.")'


def test_select_one() -> None:
    plan = {
        "intent_summary": "query customer",
        "expression_pattern": "select_one",
        "bo_refs": [{"bo_name": "CustomerBO", "field": "name", "params": []}],
    }
    agent = DSLAgent(llm_planner=LLMPlanner(StubOpenAIClient(plan_response=plan)))
    response = agent.generate_dsl(_base_request())
    assert response.success is True
    assert response.dsl == "select_one(CustomerBO.name)"


def test_function_call() -> None:
    plan = {
        "intent_summary": "call function",
        "expression_pattern": "function_call",
        "function_refs": ["str.upper"],
        "semantic_slots": {"function_args": ["$ctx$.customer.gender"]},
        "context_refs": ["$ctx$.customer.gender"],
    }
    agent = DSLAgent(llm_planner=LLMPlanner(StubOpenAIClient(plan_response=plan)))
    response = agent.generate_dsl(_base_request())
    assert response.success is True
    assert response.dsl == "str.upper($ctx$.customer.gender)"


def test_namingsql_param() -> None:
    plan = {
        "intent_summary": "fetch by ctx",
        "expression_pattern": "fetch_one",
        "context_refs": ["$ctx$.customer.id"],
        "bo_refs": [
            {
                "bo_name": "CustomerBO",
                "field": "name",
                "query_mode": "fetch_one",
                "params": [
                    {
                        "param_name": "customer_id",
                        "value": "$ctx$.customer.id",
                        "value_source_type": "context",
                    }
                ],
            }
        ],
    }
    agent = DSLAgent(llm_planner=LLMPlanner(StubOpenAIClient(plan_response=plan)))
    response = agent.generate_dsl(_base_request())
    assert response.success is True
    assert "customer_id=$ctx$.customer.id" in response.dsl


def test_context_ref() -> None:
    plan = {
        "intent_summary": "direct",
        "expression_pattern": "direct_ref",
        "context_refs": ["$ctx$.customer.id"],
    }
    agent = DSLAgent(llm_planner=LLMPlanner(StubOpenAIClient(plan_response=plan)))
    response = agent.generate_dsl(_base_request())
    assert response.success is True
    assert response.dsl == "$ctx$.customer.id"


def test_plan_validator_detect_fake_ctx() -> None:
    env = EnvironmentBuilder().build_environment(_base_request())
    validator = PlanValidator(planner=None)
    plan = {
        "intent_summary": "bad",
        "expression_pattern": "direct_ref",
        "context_refs": ["$ctx$.customer.fake"],
    }
    parsed = LLMPlanner(StubOpenAIClient(plan_response=plan)).plan("x", _base_request().node_def, env)
    result = validator.validate(parsed, env)
    assert result.is_valid is False
    assert any("fake context path" in item for item in result.issues)


def test_plan_validator_empty_param() -> None:
    env = EnvironmentBuilder().build_environment(_base_request())
    validator = PlanValidator(planner=None)
    plan = {
        "intent_summary": "bad",
        "expression_pattern": "fetch_one",
        "bo_refs": [
            {
                "bo_name": "CustomerBO",
                "field": "name",
                "params": [{"param_name": "id", "value": "", "value_source_type": "context"}],
            }
        ],
    }
    parsed = LLMPlanner(StubOpenAIClient(plan_response=plan)).plan("x", _base_request().node_def, env)
    result = validator.validate(parsed, env)
    assert result.is_valid is False
    assert any("empty namingSQL param value" in item for item in result.issues)


def test_repair_loop() -> None:
    bad_plan = {
        "intent_summary": "bad",
        "expression_pattern": "direct_ref",
        "context_refs": ["$ctx$.customer.fake"],
    }
    repaired_plan = {
        "intent_summary": "fixed",
        "expression_pattern": "direct_ref",
        "context_refs": ["$ctx$.customer.id"],
    }
    planner = LLMPlanner(StubOpenAIClient(plan_response=bad_plan, repair_response=repaired_plan))
    agent = DSLAgent(llm_planner=planner)
    response = agent.generate_dsl(_base_request())
    assert response.success is True
    assert response.plan is not None
    assert response.plan.context_refs == ["$ctx$.customer.id"]


def test_planner_payload_contains_available_functions() -> None:
    client = StubOpenAIClient(
        plan_response={
            "intent_summary": "direct",
            "expression_pattern": "direct_ref",
            "context_refs": ["$ctx$.customer.id"],
        }
    )
    planner = LLMPlanner(client)
    request = _base_request()
    request.function_schema = [
        {
            "full_name": "Customer.GetSalutation",
            "params": [{"param_name": "gender"}],
        }
    ]
    env = EnvironmentBuilder().build_environment(request)
    planner.plan("根据性别返回称谓", request.node_def, env)
    assert client.last_payload is not None
    function_candidates = client.last_payload["candidate_resources"]["function_candidates"]
    assert function_candidates == [{"name": "Customer.GetSalutation", "params": ["gender"]}]


def test_plan_validator_function_signature_check() -> None:
    env = EnvironmentBuilder().build_environment(_base_request())
    env.function_schema = [{"full_name": "str.upper", "params": ["value"]}]
    validator = PlanValidator(planner=None)
    plan = {
        "intent_summary": "call function",
        "expression_pattern": "function_call",
        "function_refs": ["str.upper"],
        "semantic_slots": {"function_args": ["$ctx$.customer.gender", "extra_arg"]},
        "context_refs": ["$ctx$.customer.gender"],
    }
    parsed = LLMPlanner(StubOpenAIClient(plan_response=plan)).plan("x", _base_request().node_def, env)
    result = validator.validate(parsed, env)
    assert result.is_valid is False
    assert any("function args mismatch" in item for item in result.issues)
