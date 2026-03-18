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
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest


def test_e2e_pipeline_minimal_working_chain_success() -> None:
    orchestrator = CodeAgentOrchestrator(
        llm_planner=LLMPlanner(
            prompt_assembler=PromptAssembler(),
            client=StubOpenAIClientAdapter(
                draft=PlanDraft(
                    intent_summary="query and format",
                    context_refs=["$ctx$.billStatement.prepareId"],
                    bo_refs=[{"bo_name": "SYS_BE", "query_mode": "select_one"}],
                    function_refs=["Common.Double2Str"],
                    expression_pattern="function_call(value)",
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
        user_requirement="use context billStatement.prepareId and select_one SYS_BE then function Common.Double2Str()",
        node_def=NodeDef(
            node_id="n1",
            node_path="/bill/value",
            node_name="value",
            data_type=DSLDataType.STRING,
        ),
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
    assert response.plan_draft is not None
    assert response.generated_dsl is not None
    assert response.dsl_code.strip() != ""
    assert "Common.Double2Str(" in response.dsl_code
    assert response.validation_result is not None and response.validation_result.is_valid is True
