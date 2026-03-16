from billing_dsl_agent.services.validator import DefaultValidator
from billing_dsl_agent.types.common import GeneratedDSL, MethodDef
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.validation import ValidationErrorCode


def _dummy_request() -> GenerateDSLRequest:
    return GenerateDSLRequest(
        user_requirement="test",
        node_def=NodeDef(node_id="n1", node_path="/a", node_name="a"),
    )


def test_validator_reports_missing_final_expression() -> None:
    validator = DefaultValidator()
    result = validator.validate(GeneratedDSL(methods=[], value_expression=""), _dummy_request(), ResolvedEnvironment())

    assert result.is_valid is False
    assert any(issue.code == ValidationErrorCode.FINAL_EXPRESSION_MISSING for issue in result.issues)


def test_validator_reports_duplicate_method_name() -> None:
    validator = DefaultValidator()
    generated = GeneratedDSL(
        methods=[MethodDef(name="dup", body="1"), MethodDef(name="dup", body="2")],
        value_expression="dup",
    )

    result = validator.validate(generated, _dummy_request(), ResolvedEnvironment())

    assert result.is_valid is False
    assert any(issue.code == ValidationErrorCode.DUPLICATE_METHOD_NAME for issue in result.issues)


def test_validator_reports_unknown_method_ref() -> None:
    validator = DefaultValidator()
    generated = GeneratedDSL(
        methods=[MethodDef(name="funcA", body="1")],
        value_expression="funcB",
    )

    result = validator.validate(generated, _dummy_request(), ResolvedEnvironment())

    assert result.is_valid is False
    assert any(issue.code == ValidationErrorCode.UNKNOWN_METHOD_REF for issue in result.issues)
