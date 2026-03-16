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
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest

_REQ = (
    "\u5bf9\u5ba2\u6237\u79f0\u8c13\u8282\u70b9\uff1a"
    "\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u7537\u65f6\uff0c\u663e\u793a\"MR.\"\uff0c"
    "\u5f53\u5ba2\u6237\u6027\u522b\u4e3a\u5973\u65f6\uff0c\u663e\u793a\"Ms.\""
)
_NODE_DESC = "\u5ba2\u6237\u79f0\u8c13\u8282\u70b9"
_MALE = "\u7537"


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


def _build_request() -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement=_REQ,
        node_def=NodeDef(
            node_id="node_customer_title",
            node_path="invoice.customer.title",
            node_name="customerTitle",
            data_type=DSLDataType.STRING,
            description=_NODE_DESC,
        ),
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                data_type=DSLDataType.OBJECT,
                description="customer global context",
                fields=[
                    ContextFieldDef(name="gender", data_type=DSLDataType.STRING),
                    ContextFieldDef(name="name", data_type=DSLDataType.STRING),
                ],
            )
        ],
        local_context_vars=[],
        available_bos=[],
        available_functions=[],
    )


def test_e2e_conditional_mapping_title_by_gender() -> None:
    orchestrator = _build_orchestrator()

    response = orchestrator.generate(_build_request())

    assert response.success is True
    assert response.dsl_code.strip() != ""
    assert response.generated_dsl is not None
    assert response.validation_result is not None
    if hasattr(response.validation_result, "is_valid"):
        assert response.validation_result.is_valid is True

    dsl_text = response.dsl_code
    assert "if(" in dsl_text
    assert "gender" in dsl_text or "customer.gender" in dsl_text
    assert _MALE in dsl_text
    assert "MR." in dsl_text
    assert "Ms." in dsl_text


def test_e2e_conditional_mapping_ast_shape() -> None:
    orchestrator = _build_orchestrator()

    response = orchestrator.generate(_build_request())

    assert response.value_plan is not None
    assert response.value_plan.final_expr is not None

    final_expr = response.value_plan.final_expr
    assert hasattr(final_expr, "kind")
    assert str(final_expr.kind).lower().endswith("if_expr")
    assert len(final_expr.children) == 3

    cond_expr, true_expr, false_expr = final_expr.children
    assert str(cond_expr.kind).lower().endswith("binary_op")
    assert str(true_expr.kind).lower().endswith("literal")
    assert str(false_expr.kind).lower().endswith("literal")
