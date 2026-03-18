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

_REQ = (
    "对客户称谓节点："
    '当客户性别为男时，显示"MR."，'
    '当客户性别为女时，显示"Ms."'
)
_NODE_DESC = "客户称谓节点"
_MALE = "男"


def _build_orchestrator() -> CodeAgentOrchestrator:
    return CodeAgentOrchestrator(
        llm_planner=LLMPlanner(
            prompt_assembler=PromptAssembler(),
            client=StubOpenAIClientAdapter(
                draft=PlanDraft(
                    intent_summary="title by gender",
                    context_refs=["$ctx$.customer.gender"],
                    semantic_slots={
                        "condition_ref": "$ctx$.customer.gender",
                        "condition_operator": "==",
                        "condition_value": _MALE,
                        "true_output": "MR.",
                        "false_output": "Ms.",
                    },
                    expression_pattern="if(condition, true, false)",
                    raw_plan={"target_node_path": "invoice.customer.title"},
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
    assert str(final_expr.kind).lower().endswith("if_expr")
    assert len(final_expr.children) == 3

    cond_expr, true_expr, false_expr = final_expr.children
    assert str(cond_expr.kind).lower().endswith("binary_op")
    assert str(true_expr.kind).lower().endswith("literal")
    assert str(false_expr.kind).lower().endswith("literal")
