from billing_dsl_agent.services import (
    CodeAgentOrchestrator,
    DefaultDSLRenderer,
    DefaultEnvironmentResolver,
    DefaultExplanationBuilder,
    DefaultValidator,
    GenerateDSLAgentService,
    LLMPlanner,
    PlanValidator,
    PromptAssembler,
    SimpleRequirementParser,
    SimpleValuePlanner,
)
from billing_dsl_agent.services.openai_client_adapter import StubOpenAIClientAdapter
from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest


def _build_request() -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement='对客户称谓节点：当客户性别为男时，显示"MR."，当客户性别为女时，显示"Ms."',
        node_def=NodeDef(
            node_id="node_customer_title",
            node_path="invoice.customer.title",
            node_name="customerTitle",
            data_type=DSLDataType.STRING,
            description="客户称谓节点",
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
    )


def _build_orchestrator(draft: PlanDraft | None) -> CodeAgentOrchestrator:
    return CodeAgentOrchestrator(
        llm_planner=LLMPlanner(
            prompt_assembler=PromptAssembler(),
            client=StubOpenAIClientAdapter(draft=draft),
            fallback_parser=SimpleRequirementParser(),
        ),
        environment_resolver=DefaultEnvironmentResolver(),
        plan_validator=PlanValidator(),
        value_planner=SimpleValuePlanner(),
        dsl_renderer=DefaultDSLRenderer(),
        validator=DefaultValidator(),
        explanation_builder=DefaultExplanationBuilder(),
    )


def test_llm_plan_to_dsl_happy_path() -> None:
    request = _build_request()
    service = GenerateDSLAgentService(
        orchestrator=_build_orchestrator(
            PlanDraft(
                intent_summary="conditional mapping by gender",
                context_refs=["$ctx$.customer.gender"],
                semantic_slots={
                    "condition_ref": "$ctx$.customer.gender",
                    "condition_operator": "==",
                    "condition_value": "男",
                    "true_output": "MR.",
                    "false_output": "Ms.",
                },
                expression_pattern="if(condition, true, false)",
                raw_plan={"target_node_path": request.node_def.node_path},
            )
        )
    )

    response = service.generate(request)

    assert response.success is True
    assert response.plan_draft is not None
    assert response.dsl_code.strip() != ""
    assert response.generated_dsl is not None
    assert response.generated_dsl.value_expression == 'if($ctx$.customer.gender == "男", "MR.", "Ms.")'


def test_fallback_to_simple_parser() -> None:
    request = _build_request()
    orchestrator = _build_orchestrator(None)

    response = orchestrator.generate(request)

    assert response.success is True
    assert response.plan_draft is not None
    assert response.plan_draft.raw_plan.get("fallback") is True
    assert "MR." in response.dsl_code
    assert "Ms." in response.dsl_code
