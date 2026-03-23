from billing_dsl_agent.services.plan_validator import PlanValidator
from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.bo import BODef, BOFieldDef
from billing_dsl_agent.types.common import ContextScope, DSLDataType, TypeRef
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.validation import ValidationErrorCode


def _env() -> ResolvedEnvironment:
    return ResolvedEnvironment(
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                data_type=DSLDataType.OBJECT,
                fields=[ContextFieldDef(name="gender", data_type=DSLDataType.STRING)],
            )
        ],
        available_bos=[
            BODef(
                id="bo_1",
                name="BB_PREP_SUB",
                fields=[BOFieldDef(name="regionId", type=TypeRef(kind="basic", name="string"))],
            )
        ],
        available_functions=[FunctionDef(id="fn_1", class_name="Common", method_name="Double2Str")],
    )


def test_plan_validator_detect_invalid_context() -> None:
    validator = PlanValidator()
    plan = PlanDraft(
        intent_summary="invalid context",
        context_refs=["$ctx$.customer.unknownField"],
        expression_pattern="direct_ref",
    )

    result = validator.validate(plan, _env())

    assert result.is_valid is False
    assert any(issue.code == ValidationErrorCode.UNKNOWN_CONTEXT_VAR for issue in result.issues)


def test_plan_validator_detect_invalid_bo() -> None:
    validator = PlanValidator()
    plan = PlanDraft(
        intent_summary="invalid bo",
        bo_refs=[{"bo_name": "UNKNOWN_BO", "query_mode": "select_one", "field": "regionId"}],
        expression_pattern="query(field)",
    )

    result = validator.validate(plan, _env())

    assert result.is_valid is False
    assert any(issue.code == ValidationErrorCode.UNKNOWN_BO for issue in result.issues)
