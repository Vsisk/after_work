import pytest
from pydantic import ValidationError

from billing_dsl_agent.models import ProgramPlan
from billing_dsl_agent.plan_validator import adapt_legacy_plan, parse_program_plan_payload


def test_program_plan_parses_without_definitions() -> None:
    plan = ProgramPlan.model_validate(
        {
            "definitions": [],
            "return_expr": {"type": "literal", "value": "ok"},
        }
    )
    assert plan.definitions == []
    assert plan.return_expr.type == "literal"


def test_program_plan_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProgramPlan.model_validate(
            {
                "definitions": [],
                "return_expr": {"type": "literal", "value": "ok", "extra": True},
            }
        )


def test_expr_tree_only_payload_is_adapted_to_program_plan() -> None:
    plan = adapt_legacy_plan(
        {
            "expr_tree": {
                "type": "function_call",
                "function_name": "Customer.GetSalutation",
                "args": [{"type": "context_ref", "path": "$ctx$.customer.gender"}],
            }
        }
    )
    assert plan.definitions == []
    assert plan.return_expr.type == "function_call"
    assert plan.return_expr.args[0].type == "context_ref"


def test_legacy_plan_payload_is_adapted_to_program_plan() -> None:
    plan = parse_program_plan_payload(
        {
            "intent_summary": "function call",
            "expression_pattern": "function_call",
            "context_refs": ["context:$ctx$.customer.gender"],
            "function_refs": ["function:Customer.GetSalutation"],
            "semantic_slots": {"function_args": ["context:$ctx$.customer.gender"]},
        }
    )
    assert plan.legacy_plan is not None
    assert plan.return_expr.type == "function_call"
    assert plan.return_expr.function_name == "Customer.GetSalutation"
