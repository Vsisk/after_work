import pytest
from pydantic import ValidationError

from billing_dsl_agent.models import ProgramPlan
from billing_dsl_agent.plan_validator import parse_program_plan_payload


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


def test_parse_program_plan_payload_requires_current_schema() -> None:
    plan = parse_program_plan_payload(
        {
            "definitions": [],
            "return_expr": {"type": "function_call", "function_id": "function:Customer.GetSalutation", "args": []},
        }
    )
    assert plan.return_expr.type == "function_call"


def test_parse_program_plan_payload_rejects_legacy_shape() -> None:
    with pytest.raises(ValidationError):
        parse_program_plan_payload({"expression_pattern": "function_call"})
