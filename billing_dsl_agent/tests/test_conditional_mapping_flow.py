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
from billing_dsl_agent.types.dsl import ExprKind, ExprNode, ValuePlan
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.request_response import GenerateDSLRequest


def _node_def() -> NodeDef:
    return NodeDef(node_id="n1", node_path="/customer/title", node_name="title", data_type=DSLDataType.STRING)


def test_parse_conditional_mapping_requirement() -> None:
    planner = LLMPlanner(
        prompt_assembler=PromptAssembler(),
        client=StubOpenAIClientAdapter(
            draft=PlanDraft(
                intent_summary="title by gender",
                context_refs=["$ctx$.customer.gender"],
                semantic_slots={
                    "condition_ref": "$ctx$.customer.gender",
                    "condition_operator": "==",
                    "condition_value": "男",
                    "true_output": "MR.",
                    "false_output": "Ms.",
                },
                expression_pattern="if(condition, true, false)",
            )
        ),
        fallback_parser=SimpleRequirementParser(),
    )
    plan = planner.plan(
        user_requirement='当客户性别为男时，显示"MR."，当客户性别为女时，显示"Ms."',
        node_def=_node_def(),
        env=ResolvedEnvironment(),
    )

    assert plan.context_refs == ["$ctx$.customer.gender"]
    assert plan.semantic_slots.get("condition_value") == "男"
    assert plan.semantic_slots.get("true_output") == "MR."
    assert plan.semantic_slots.get("false_output") == "Ms."


def test_match_condition_field_from_context() -> None:
    validator = PlanValidator()
    plan = PlanDraft(
        intent_summary="title by gender",
        context_refs=["$ctx$.customer.gender"],
        semantic_slots={"condition_value": "男"},
        expression_pattern="if(condition, true, false)",
    )
    env = ResolvedEnvironment(
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                fields=[ContextFieldDef(name="gender")],
            )
        ]
    )

    result = validator.validate(plan, env)

    assert result.is_valid is True


def test_plan_conditional_mapping_ast() -> None:
    planner = SimpleValuePlanner()
    draft = PlanDraft(
        intent_summary="title by gender",
        context_refs=["$ctx$.customer.gender"],
        semantic_slots={
            "condition_ref": "$ctx$.customer.gender",
            "condition_operator": "==",
            "condition_value": "男",
            "true_output": "MR.",
            "false_output": "Ms.",
        },
        expression_pattern="if(condition, true, false)",
    )

    plan = planner.build_plan(draft, ResolvedEnvironment())

    assert plan.final_expr is not None
    assert plan.final_expr.kind == ExprKind.IF_EXPR
    assert plan.final_expr.children[0].kind == ExprKind.BINARY_OP
    assert plan.final_expr.children[1].kind == ExprKind.LITERAL
    assert plan.final_expr.children[2].kind == ExprKind.LITERAL


def test_render_conditional_mapping_expression() -> None:
    renderer = DefaultDSLRenderer()
    plan = ValuePlan(
        target_node_path="/customer/title",
        final_expr=ExprNode(
            kind=ExprKind.IF_EXPR,
            children=[
                ExprNode(
                    kind=ExprKind.BINARY_OP,
                    value="==",
                    children=[
                        ExprNode(kind=ExprKind.CONTEXT_REF, value="$ctx$.customer.gender"),
                        ExprNode(kind=ExprKind.LITERAL, value="男"),
                    ],
                ),
                ExprNode(kind=ExprKind.LITERAL, value="MR."),
                ExprNode(kind=ExprKind.LITERAL, value="Ms."),
            ],
        ),
    )

    generated = renderer.render(plan)

    assert generated.value_expression.startswith("if(")
    assert '== "男"' in generated.value_expression
    assert '"MR."' in generated.value_expression
    assert '"Ms."' in generated.value_expression


def test_orchestrator_happy_path_for_conditional_mapping() -> None:
    orchestrator = CodeAgentOrchestrator(
        llm_planner=LLMPlanner(
            prompt_assembler=PromptAssembler(),
            client=StubOpenAIClientAdapter(
                draft=PlanDraft(
                    intent_summary="title by gender",
                    context_refs=["$ctx$.customer.gender"],
                    semantic_slots={
                        "condition_ref": "$ctx$.customer.gender",
                        "condition_operator": "==",
                        "condition_value": "男",
                        "true_output": "MR.",
                        "false_output": "Ms.",
                    },
                    expression_pattern="if(condition, true, false)",
                    raw_plan={"target_node_path": "/customer/title"},
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
        user_requirement='当客户性别为男时，显示"MR."，当客户性别为女时，显示"Ms."',
        node_def=_node_def(),
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                fields=[ContextFieldDef(name="gender")],
            )
        ],
    )

    response = orchestrator.generate(request)

    assert response.success is True
    assert response.dsl_code.strip() != ""
    assert "if(" in response.dsl_code
    assert "MR." in response.dsl_code or "Ms." in response.dsl_code
