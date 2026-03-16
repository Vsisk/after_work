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
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest


def test_e2e_pipeline_minimal_working_chain_success() -> None:
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
    assert response.generated_dsl is not None
    assert "select_one(SYS_BE" in response.dsl_code
    assert "Common.Double2Str(" in response.dsl_code
    assert response.validation_result is not None and response.validation_result.is_valid is True
