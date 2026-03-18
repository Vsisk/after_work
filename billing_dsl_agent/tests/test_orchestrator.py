from billing_dsl_agent.services import (
    CodeAgentOrchestrator,
    DefaultDSLRenderer,
    DefaultEnvironmentResolver,
    DefaultExplanationBuilder,
    DefaultValidator,
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


def test_orchestrator_happy_path() -> None:
    orchestrator = CodeAgentOrchestrator(
        llm_planner=LLMPlanner(
            prompt_assembler=PromptAssembler(),
            client=StubOpenAIClientAdapter(
                draft=PlanDraft(
                    intent_summary="format gender title",
                    context_refs=["$ctx$.customer.gender"],
                    semantic_slots={
                        "condition_ref": "$ctx$.customer.gender",
                        "condition_operator": "==",
                        "condition_value": "男",
                        "true_output": "MR.",
                        "false_output": "Ms.",
                    },
                    expression_pattern="if(condition, true, false)",
                    raw_plan={"target_node_path": "/bill/value"},
                )
            ),
            fallback_parser=SimpleRequirementParser(),
        ),
        environment_resolver=DefaultEnvironmentResolver(),
        plan_validator=PlanValidator(),
        value_planner=SimpleValuePlanner(),
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
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                fields=[ContextFieldDef(name="gender", data_type=DSLDataType.STRING)],
            )
        ],
    )

    response = orchestrator.generate(request)

    assert response.success is True
    assert response.plan_draft is not None
    assert response.validation_result is not None and response.validation_result.is_valid is True
    assert response.explanation is not None
