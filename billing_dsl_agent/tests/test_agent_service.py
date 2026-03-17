from billing_dsl_agent.services import (
    CodeAgentOrchestrator,
    DefaultDSLRenderer,
    DefaultEnvironmentResolver,
    DefaultExplanationBuilder,
    DefaultResourceMatcher,
    DefaultValidator,
    GenerateDSLAgentService,
    LLMRequirementParser,
    PromptAssembler,
    SimpleRequirementParser,
    SimpleValuePlanner,
)
from billing_dsl_agent.services.openai_client_adapter import StubOpenAIClientAdapter
from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.intent import IntentSourceType
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest


def _build_request() -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement="\u5bf9\u5ba2\u6237\u79f0\u8c13\u8282\u70b9\uff1a\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u7537\u65f6\uff0c\u663e\u793a\"MR.\"\uff0c\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u5973\u65f6\uff0c\u663e\u793a\"Ms.\"",
        node_def=NodeDef(
            node_id="node_customer_title",
            node_path="invoice.customer.title",
            node_name="customerTitle",
            data_type=DSLDataType.STRING,
            description="\u5ba2\u6237\u79f0\u8c13\u8282\u70b9",
        ),
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                data_type=DSLDataType.OBJECT,
                fields=[
                    ContextFieldDef(name="gender", data_type=DSLDataType.STRING),
                    ContextFieldDef(name="name", data_type=DSLDataType.STRING),
                ],
            )
        ],
        local_context_vars=[],
        available_bos=[BODef(id="bo_1", name="BB_PREP_SUB")],
        available_functions=[FunctionDef(id="fn_1", class_name="Common", method_name="Double2Str")],
    )


def _build_orchestrator() -> CodeAgentOrchestrator:
    return CodeAgentOrchestrator(
        parser=SimpleRequirementParser(),
        environment_resolver=DefaultEnvironmentResolver(),
        resource_matcher=DefaultResourceMatcher(),
        value_planner=SimpleValuePlanner(),
        dsl_renderer=DefaultDSLRenderer(),
        validator=DefaultValidator(),
        explanation_builder=DefaultExplanationBuilder(),
    )


def test_prompt_assembler_builds_payload() -> None:
    assembler = PromptAssembler()

    payload = assembler.build_payload(_build_request(), model="gpt-4.1-mini")

    assert payload["model"] == "gpt-4.1-mini"
    assert len(payload["messages"]) == 2
    assert "Requirement:" in payload["messages"][1]["content"]
    assert "invoice.customer.title" in payload["messages"][1]["content"]
    assert "customer(gender, name)" in payload["messages"][1]["content"]
    assert "Common.Double2Str" in payload["messages"][1]["content"]


def test_llm_parser_fallback_to_simple_parser() -> None:
    parser = LLMRequirementParser(
        prompt_assembler=PromptAssembler(),
        client=StubOpenAIClientAdapter(draft=None),
        fallback_parser=SimpleRequirementParser(),
    )

    intent = parser.parse_request(_build_request())

    assert IntentSourceType.CONDITIONAL in intent.source_types
    assert intent.semantic_slots.get("conditional_mapping") is True
    assert intent.semantic_slots.get("condition_field_hint") == "\u5ba2\u6237\u6027\u522b"
    assert intent.semantic_slots.get("true_output") == "MR."
    assert intent.semantic_slots.get("false_output") == "Ms."


def test_generate_dsl_agent_service_happy_path_with_mock_client() -> None:
    request = _build_request()
    llm_parser = LLMRequirementParser(
        prompt_assembler=PromptAssembler(),
        client=StubOpenAIClientAdapter(
            draft=PlanDraft(
                intent_summary="conditional mapping by gender",
                semantic_slots={
                    "conditional_mapping": True,
                    "condition_field_hint": "\u5ba2\u6237\u6027\u522b",
                    "condition_operator": "==",
                    "condition_value": "\u7537",
                    "true_output": "MR.",
                    "false_output": "Ms.",
                    "context_field_hints": ["gender"],
                },
                candidate_resources={"context": ["customer.gender"]},
                expression_pattern="if(condition, true_expr, false_expr)",
                source_types=["CONTEXT", "CONDITIONAL"],
                operations=["build_conditional_mapping"],
            )
        ),
        fallback_parser=SimpleRequirementParser(),
    )
    service = GenerateDSLAgentService(
        orchestrator=_build_orchestrator(),
        llm_parser=llm_parser,
        enable_llm_parser=True,
    )

    response = service.generate(request)

    assert response.success is True
    assert response.intent is not None
    assert response.intent.semantic_slots.get("conditional_mapping") is True
    assert response.dsl_code.strip() != ""
    assert "if(" in response.dsl_code
    assert "MR." in response.dsl_code
    assert "Ms." in response.dsl_code
