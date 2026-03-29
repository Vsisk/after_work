from billing_dsl_agent.ast_builder import ASTBuilder
from billing_dsl_agent.dsl_renderer import DSLRenderer
from billing_dsl_agent.models import FilteredEnvironment, ProgramPlan, ResourceRegistry


def _env() -> FilteredEnvironment:
    return FilteredEnvironment(registry=ResourceRegistry())


def test_ast_builder_builds_program_defs_and_return() -> None:
    plan = ProgramPlan.model_validate(
        {
            "definitions": [
                {
                    "kind": "variable",
                    "name": "customer_gender",
                    "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                },
                {
                    "kind": "variable",
                    "name": "title_prefix",
                    "expr": {
                        "type": "if",
                        "condition": {
                            "type": "binary_op",
                            "operator": "==",
                            "left": {"type": "var_ref", "name": "customer_gender"},
                            "right": {"type": "literal", "value": "M"},
                        },
                        "then_expr": {"type": "literal", "value": "MR."},
                        "else_expr": {"type": "literal", "value": "MS."},
                    },
                },
            ],
            "return_expr": {"type": "var_ref", "name": "title_prefix"},
        }
    )

    program = ASTBuilder().build_program_from_plan(plan, _env())
    rendered = DSLRenderer().render(program)

    assert len(program.definitions) == 2
    assert program.definitions[0].name == "customer_gender"
    assert program.return_node.expr.kind.value == "VAR_REF"
    assert rendered.splitlines() == [
        "def customer_gender = $ctx$.customer.gender",
        'def title_prefix = if(customer_gender == "M", "MR.", "MS.")',
        "title_prefix",
    ]
