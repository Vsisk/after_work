from billing_dsl_agent.models import (
    FilteredEnvironment,
    FunctionCallPlanNode,
    FunctionParamResource,
    FunctionResource,
    LiteralPlanNode,
    NormalizedTypeRef,
    ProgramPlan,
    ResourceRegistry,
    ValidationIssue,
)
from billing_dsl_agent.plan_validator import validate_program_plan_semantics


def _build_function(
    *,
    resource_id: str,
    full_name: str,
    params: list[FunctionParamResource],
    return_type_raw: str = "String",
) -> FunctionResource:
    return FunctionResource(
        resource_id=resource_id,
        function_id=resource_id,
        name=full_name.split(".")[-1],
        full_name=full_name,
        description="",
        function_kind="func",
        signature=f"{full_name}({', '.join([p.param_name for p in params])})",
        signature_display=f"{full_name}(" + ", ".join([f"{p.param_name}:{p.normalized_param_type}" for p in params]) + ")",
        params=[p.param_name for p in params],
        param_defs=params,
        return_type_raw=return_type_raw,
        return_type="string",
    )


def _build_env(functions: list[FunctionResource]) -> FilteredEnvironment:
    function_map = {item.resource_id: item for item in functions}
    registry = ResourceRegistry(functions=function_map)
    return FilteredEnvironment(registry=registry, selected_function_ids=list(function_map.keys()))


def _codes(issues: list[ValidationIssue]) -> set[str]:
    return {item.code for item in issues}


def test_function_resolve_by_id_and_name() -> None:
    param = FunctionParamResource(
        param_id="p1",
        param_name="gender",
        param_type_raw="String",
        normalized_param_type="string",
        type_ref=NormalizedTypeRef(raw_type="String", normalized_type="string", category="basic", is_unknown=False),
    )
    fn = _build_function(resource_id="function:Customer.GetSalutation", full_name="Customer.GetSalutation", params=[param])
    env = _build_env([fn])
    plan = ProgramPlan(
        definitions=[],
        return_expr=FunctionCallPlanNode(
            type="function_call",
            function_name="GetSalutation",
            args=[LiteralPlanNode(type="literal", value="M")],
        ),
    )
    issues = validate_program_plan_semantics(plan, env)
    assert _codes(issues) == set()


def test_function_signature_validates_arg_count() -> None:
    param = FunctionParamResource(
        param_id="p1",
        param_name="gender",
        param_type_raw="String",
        normalized_param_type="string",
        type_ref=NormalizedTypeRef(raw_type="String", normalized_type="string", category="basic", is_unknown=False),
    )
    fn = _build_function(resource_id="function:Customer.GetSalutation", full_name="Customer.GetSalutation", params=[param])
    env = _build_env([fn])
    plan = ProgramPlan(definitions=[], return_expr=FunctionCallPlanNode(type="function_call", function_id=fn.resource_id, args=[]))
    issues = validate_program_plan_semantics(plan, env)
    assert "function_args_mismatch" in _codes(issues)


def test_function_signature_validates_basic_type_match() -> None:
    param = FunctionParamResource(
        param_id="p1",
        param_name="count",
        param_type_raw="int",
        normalized_param_type="int",
        type_ref=NormalizedTypeRef(raw_type="int", normalized_type="int", category="basic", is_unknown=False),
    )
    fn = _build_function(resource_id="function:Counter.FromCount", full_name="Counter.FromCount", params=[param])
    env = _build_env([fn])
    plan = ProgramPlan(
        definitions=[],
        return_expr=FunctionCallPlanNode(
            type="function_call",
            function_id=fn.resource_id,
            args=[LiteralPlanNode(type="literal", value="not-int")],
        ),
    )
    issues = validate_program_plan_semantics(plan, env)
    assert "function_arg_type_mismatch" in _codes(issues)


def test_function_signature_reports_unknown_param_type_as_warning() -> None:
    param = FunctionParamResource(
        param_id="p1",
        param_name="payload",
        param_type_raw="",
        normalized_param_type="unknown",
        type_ref=NormalizedTypeRef(raw_type="", normalized_type="unknown", category="unknown", is_unknown=True),
    )
    fn = _build_function(resource_id="function:Mask.CustCallMask", full_name="Mask.CustCallMask", params=[param])
    env = _build_env([fn])
    plan = ProgramPlan(
        definitions=[],
        return_expr=FunctionCallPlanNode(
            type="function_call",
            function_id=fn.resource_id,
            args=[LiteralPlanNode(type="literal", value=1)],
        ),
    )
    issues = validate_program_plan_semantics(plan, env)
    warning_issues = [item for item in issues if item.code == "function_param_type_unknown"]
    assert warning_issues
    assert all(item.severity == "warning" for item in warning_issues)
