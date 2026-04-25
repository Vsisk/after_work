from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    FilteredEnvironment,
    FunctionResource,
    NormalizedNamingSQLDef,
    NormalizedNamingSQLParam,
    NormalizedNamingTypeRef,
    NormalizedLocalContextNode,
    ProgramPlan,
    ProgramPlanLimits,
    ResourceRegistry,
    VisibleLocalContextSet,
)
from pydantic import ValidationError
from billing_dsl_agent.plan_validator import (
    PlanValidator,
    compare_namingsql_param_type,
    validate_program_plan_structure,
)


def _env() -> FilteredEnvironment:
    registry = ResourceRegistry(
        contexts={
            "context:$ctx$.customer.id": ContextResource(
                resource_id="context:$ctx$.customer.id",
                name="id",
                path="$ctx$.customer.id",
                scope="global",
            ),
            "context:$ctx$.customer.gender": ContextResource(
                resource_id="context:$ctx$.customer.gender",
                name="gender",
                path="$ctx$.customer.gender",
                scope="global",
            ),
        },
        bos={
            "bo:CustomerBO": BOResource(
                resource_id="bo:CustomerBO",
                bo_name="CustomerBO",
                field_ids=[
                    "bo:CustomerBO:field:id",
                    "bo:CustomerBO:field:gender",
                    "bo:CustomerBO:field:name",
                ],
                data_source="crm",
                naming_sql_ids=["bo:CustomerBO:sql:findById"],
                naming_sqls=[
                    NormalizedNamingSQLDef(
                        naming_sql_id="bo:CustomerBO:sql:findById",
                        naming_sql_name="findById",
                        bo_id="bo:CustomerBO",
                        params=[
                            NormalizedNamingSQLParam(
                                param_id="findById:0",
                                param_name="id",
                                data_type="basic",
                                data_type_name="INT64",
                                is_list=False,
                                normalized_type_ref=NormalizedNamingTypeRef(
                                    data_type="basic",
                                    data_type_name="INT64",
                                    is_list=False,
                                    is_unknown=False,
                                ),
                            )
                        ],
                    )
                ],
                naming_sqls_by_id={
                    "bo:CustomerBO:sql:findById": NormalizedNamingSQLDef(
                        naming_sql_id="bo:CustomerBO:sql:findById",
                        naming_sql_name="findById",
                        bo_id="bo:CustomerBO",
                        params=[
                            NormalizedNamingSQLParam(
                                param_id="findById:0",
                                param_name="id",
                                data_type="basic",
                                data_type_name="INT64",
                                is_list=False,
                                normalized_type_ref=NormalizedNamingTypeRef(
                                    data_type="basic",
                                    data_type_name="INT64",
                                    is_list=False,
                                    is_unknown=False,
                                ),
                            )
                        ],
                    )
                },
                naming_sql_name_by_key={
                    "bo:CustomerBO:sql:findById": "findById",
                    "findById": "findById",
                },
            )
        },
        functions={
            "function:Customer.GetSalutation": FunctionResource(
                resource_id="function:Customer.GetSalutation",
                function_id="Customer.GetSalutation",
                name="GetSalutation",
                full_name="Customer.GetSalutation",
                params=["gender"],
                return_type="string",
            )
        },
    )
    return FilteredEnvironment(
        registry=registry,
        selected_global_context_ids=[
            "context:$ctx$.customer.id",
            "context:$ctx$.customer.gender",
        ],
        selected_local_context_ids=["local_context:lc_invoice_id"],
        selected_bo_ids=["bo:CustomerBO"],
        selected_function_ids=["function:Customer.GetSalutation"],
        visible_local_context=VisibleLocalContextSet(
            nodes_by_id={
                "local_context:lc_invoice_id": NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            },
            nodes_by_property_name={
                "invoiceId": NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            },
            ordered_nodes=[
                NormalizedLocalContextNode(
                    resource_id="local_context:lc_invoice_id",
                    property_id="lc_invoice_id",
                    property_name="invoiceId",
                    access_path="$local$.invoiceId",
                )
            ],
        ),
    )


def _plan(payload: dict) -> ProgramPlan:
    return ProgramPlan.model_validate(payload)


def _deep_literal(depth: int) -> dict:
    if depth <= 1:
        return {"type": "literal", "value": 1}
    return {
        "type": "binary_op",
        "operator": "+",
        "left": {"type": "literal", "value": depth},
        "right": _deep_literal(depth - 1),
    }


def test_simple_return_expr_program_is_valid() -> None:
    plan = _plan({"definitions": [], "return_expr": {"type": "context_ref", "path": "$ctx$.customer.gender"}})
    result = PlanValidator(planner=None).validate(plan, _env())
    assert result.is_valid is True


def test_single_definition_and_return_expr_is_valid() -> None:
    plan = _plan(
        {
            "definitions": [
                {
                    "kind": "variable",
                    "name": "customer_gender",
                    "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                }
            ],
            "return_expr": {"type": "var_ref", "name": "customer_gender"},
        }
    )
    result = PlanValidator(planner=None).validate(plan, _env())
    assert result.is_valid is True


def test_chained_variable_definitions_are_valid() -> None:
    plan = _plan(
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
    result = PlanValidator(planner=None).validate(plan, _env())
    assert result.is_valid is True


def test_undefined_var_ref_fails() -> None:
    plan = _plan({"definitions": [], "return_expr": {"type": "var_ref", "name": "missing_name"}})
    issues = PlanValidator(planner=None).validate(plan, _env()).issues
    assert any(item.code == "undefined_var_ref" for item in issues)


def test_forward_var_ref_fails() -> None:
    plan = _plan(
        {
            "definitions": [
                {
                    "kind": "variable",
                    "name": "title_prefix",
                    "expr": {"type": "var_ref", "name": "customer_gender"},
                },
                {
                    "kind": "variable",
                    "name": "customer_gender",
                    "expr": {"type": "context_ref", "path": "$ctx$.customer.gender"},
                },
            ],
            "return_expr": {"type": "var_ref", "name": "title_prefix"},
        }
    )
    issues = PlanValidator(planner=None).validate(plan, _env()).issues
    assert any(item.code == "forward_var_ref" for item in issues)


def test_duplicate_definition_name_fails() -> None:
    plan = _plan(
        {
            "definitions": [
                {"kind": "variable", "name": "dup_name", "expr": {"type": "literal", "value": 1}},
                {"kind": "variable", "name": "dup_name", "expr": {"type": "literal", "value": 2}},
            ],
            "return_expr": {"type": "literal", "value": 1},
        }
    )
    issues = PlanValidator(planner=None).validate(plan, _env()).issues
    assert any(item.code == "duplicate_definition_name" for item in issues)


def test_invalid_definition_name_fails() -> None:
    plan = _plan(
        {
            "definitions": [{"kind": "variable", "name": "1bad", "expr": {"type": "literal", "value": 1}}],
            "return_expr": {"type": "literal", "value": 1},
        }
    )
    issues = PlanValidator(planner=None).validate(plan, _env()).issues
    assert any(item.code == "invalid_definition_name" for item in issues)


def test_definitions_count_limit_fails() -> None:
    definitions = [
        {"kind": "variable", "name": f"value_{index}", "expr": {"type": "literal", "value": index}}
        for index in range(7)
    ]
    plan = _plan({"definitions": definitions, "return_expr": {"type": "literal", "value": 1}})
    issues = validate_program_plan_structure(plan, ProgramPlanLimits(max_definitions=6))
    assert any(item.code == "too_many_definitions" for item in issues)


def test_definition_expr_depth_limit_fails() -> None:
    plan = _plan(
        {
            "definitions": [{"kind": "variable", "name": "deep_value", "expr": _deep_literal(6)}],
            "return_expr": {"type": "var_ref", "name": "deep_value"},
        }
    )
    issues = validate_program_plan_structure(plan, ProgramPlanLimits(max_expr_depth_per_definition=4))
    assert any(item.code == "definition_expr_depth_exceeded" for item in issues)


def test_return_expr_depth_limit_fails() -> None:
    plan = _plan({"definitions": [], "return_expr": _deep_literal(6)})
    issues = validate_program_plan_structure(plan, ProgramPlanLimits(max_return_expr_depth=5))
    assert any(item.code == "return_expr_depth_exceeded" for item in issues)


def test_total_expr_nodes_limit_fails() -> None:
    plan = _plan(
        {
            "definitions": [
                {"kind": "variable", "name": "a", "expr": _deep_literal(4)},
                {"kind": "variable", "name": "b", "expr": _deep_literal(4)},
            ],
            "return_expr": _deep_literal(4),
        }
    )
    issues = validate_program_plan_structure(plan, ProgramPlanLimits(max_total_expr_nodes=10))
    assert any(item.code == "total_expr_nodes_exceeded" for item in issues)


def test_definition_cycle_fails() -> None:
    plan = _plan(
        {
            "definitions": [
                {"kind": "variable", "name": "a", "expr": {"type": "var_ref", "name": "b"}},
                {"kind": "variable", "name": "b", "expr": {"type": "var_ref", "name": "a"}},
            ],
            "return_expr": {"type": "var_ref", "name": "a"},
        }
    )
    issues = validate_program_plan_structure(plan, ProgramPlanLimits())
    assert any(item.code == "definition_cycle" for item in issues)


def test_method_definition_shape_is_rejected_by_schema() -> None:
    try:
        _plan(
            {
                "definitions": [
                    {
                        "kind": "method",
                        "name": "format_title",
                        "params": ["gender"],
                        "body": {"type": "var_ref", "name": "gender"},
                    }
                ],
                "return_expr": {"type": "literal", "value": 1},
            }
        )
    except ValidationError:
        return
    raise AssertionError("method definition payload should be rejected")


def test_compare_namingsql_param_type_ordered_match() -> None:
    expected = NormalizedNamingTypeRef(data_type="basic", data_type_name="Date", is_list=False, is_unknown=False)
    actual = NormalizedNamingTypeRef(data_type="basic", data_type_name="Date", is_list=False, is_unknown=False)
    result = compare_namingsql_param_type(expected, actual)
    assert result.matched is True


def test_compare_namingsql_param_type_data_type_mismatch() -> None:
    expected = NormalizedNamingTypeRef(data_type="bo", data_type_name="BB_BILL_INVOICE", is_list=False, is_unknown=False)
    actual = NormalizedNamingTypeRef(data_type="logic", data_type_name="BB_BILL_INVOICE", is_list=False, is_unknown=False)
    result = compare_namingsql_param_type(expected, actual)
    assert result.matched is False
    assert result.mismatch_stage == "data_type"


def test_compare_namingsql_param_type_data_type_name_mismatch() -> None:
    expected = NormalizedNamingTypeRef(data_type="basic", data_type_name="Date", is_list=False, is_unknown=False)
    actual = NormalizedNamingTypeRef(data_type="basic", data_type_name="String", is_list=False, is_unknown=False)
    result = compare_namingsql_param_type(expected, actual)
    assert result.matched is False
    assert result.mismatch_stage == "data_type_name"


def test_compare_namingsql_param_type_is_list_mismatch() -> None:
    expected = NormalizedNamingTypeRef(data_type="basic", data_type_name="Date", is_list=False, is_unknown=False)
    actual = NormalizedNamingTypeRef(data_type="basic", data_type_name="Date", is_list=True, is_unknown=False)
    result = compare_namingsql_param_type(expected, actual)
    assert result.matched is False
    assert result.mismatch_stage == "is_list"


def test_fetch_namingsql_param_count_and_signature_checks() -> None:
    plan = _plan(
        {
            "definitions": [],
            "return_expr": {
                "type": "query_call",
                "query_kind": "fetch_one",
                "bo_id": "bo:CustomerBO",
                "source_name": "findById",
                "naming_sql_id": "bo:CustomerBO:sql:findById",
                "pairs": [{"key": "id", "value": {"type": "literal", "value": 1001}}],
            },
        }
    )
    result = PlanValidator(planner=None).validate(plan, _env())
    assert result.is_valid is True


def test_fetch_namingsql_param_count_mismatch() -> None:
    plan = _plan(
        {
            "definitions": [],
            "return_expr": {
                "type": "query_call",
                "query_kind": "fetch_one",
                "bo_id": "bo:CustomerBO",
                "source_name": "findById",
                "naming_sql_id": "bo:CustomerBO:sql:findById",
                "pairs": [],
            },
        }
    )
    issues = PlanValidator(planner=None).validate(plan, _env()).issues
    assert any(item.code == "naming_sql_param_mismatch" for item in issues)


def test_fetch_namingsql_missing_expected_type_warns() -> None:
    env = _env()
    env.registry.bos["bo:CustomerBO"].naming_sqls_by_id["bo:CustomerBO:sql:findById"] = NormalizedNamingSQLDef(
        naming_sql_id="bo:CustomerBO:sql:findById",
        naming_sql_name="findById",
        bo_id="bo:CustomerBO",
        params=[
            NormalizedNamingSQLParam(
                param_id="findById:0",
                param_name="id",
                data_type="",
                data_type_name="",
                is_list=None,
                normalized_type_ref=NormalizedNamingTypeRef(data_type="", data_type_name="", is_list=None, is_unknown=True),
            )
        ],
    )
    plan = _plan(
        {
            "definitions": [],
            "return_expr": {
                "type": "query_call",
                "query_kind": "fetch_one",
                "bo_id": "bo:CustomerBO",
                "source_name": "findById",
                "naming_sql_id": "bo:CustomerBO:sql:findById",
                "pairs": [{"key": "id", "value": {"type": "literal", "value": 1001}}],
            },
        }
    )
    issues = PlanValidator(planner=None).validate(plan, env).issues
    assert any(item.code == "naming_sql_param_data_type_missing" and item.severity == "warning" for item in issues)
    assert any(item.code == "naming_sql_param_data_type_name_missing" and item.severity == "warning" for item in issues)
