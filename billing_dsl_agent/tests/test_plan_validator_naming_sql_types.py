from billing_dsl_agent.models import (
    BOResource,
    FilteredEnvironment,
    LiteralPlanNode,
    ProgramPlan,
    QueryCallPlanNode,
    QueryPairPlanNode,
    ResourceRegistry,
)
from billing_dsl_agent.plan_validator import PlanValidator, compare_namingsql_param_type


def _env_with_naming_sql(param_meta: list[dict]) -> FilteredEnvironment:
    bo = BOResource(
        resource_id="bo:InvoiceBO",
        bo_name="InvoiceBO",
        field_ids=[],
        data_source="",
        naming_sql_ids=["bo:InvoiceBO:sql:queryInvoice"],
        naming_sql_name_by_key={
            "invoice_query_001": "queryInvoice",
            "queryInvoice": "queryInvoice",
            "bo:InvoiceBO:sql:queryInvoice": "queryInvoice",
        },
        naming_sql_param_names_by_key={
            "invoice_query_001": [item.get("param_name", "") for item in param_meta],
            "queryInvoice": [item.get("param_name", "") for item in param_meta],
        },
        naming_sql_param_meta_by_key={
            "invoice_query_001": param_meta,
            "queryInvoice": param_meta,
        },
    )
    registry = ResourceRegistry(bos={"bo:InvoiceBO": bo})
    return FilteredEnvironment(
        registry=registry,
        selected_global_context_ids=[],
        selected_local_context_ids=[],
        selected_bo_ids=["bo:InvoiceBO"],
        selected_function_ids=[],
    )


def test_compare_namingsql_param_type_ordered_rules() -> None:
    expected = {"data_type": "basic", "data_type_name": "Date", "is_list": False}

    assert compare_namingsql_param_type(expected, {"data_type": "basic", "data_type_name": "Date", "is_list": False}).is_match
    assert compare_namingsql_param_type(expected, {"data_type": "bo", "data_type_name": "Date", "is_list": False}).stage == "data_type"
    assert compare_namingsql_param_type(expected, {"data_type": "basic", "data_type_name": "String", "is_list": False}).stage == "data_type_name"
    assert compare_namingsql_param_type(expected, {"data_type": "basic", "data_type_name": "Date", "is_list": True}).stage == "is_list"


def test_validator_checks_naming_sql_signature_presence_and_param_count() -> None:
    env = _env_with_naming_sql(
        [
            {"param_name": "END_DATE", "data_type": "basic", "data_type_name": "Date", "is_list": False},
            {"param_name": "ID", "data_type": "basic", "data_type_name": "String", "is_list": False},
        ]
    )
    plan = ProgramPlan(
        definitions=[],
        return_expr=QueryCallPlanNode(
            type="query_call",
            query_kind="fetch_one",
            source_name="InvoiceBO",
            bo_id="bo:InvoiceBO",
            naming_sql_id="invoice_query_001",
            pairs=[QueryPairPlanNode(key="END_DATE", value=LiteralPlanNode(type="literal", value="2026-01-01"))],
        ),
    )

    result = PlanValidator().validate(plan, env)
    assert result.is_valid is False
    assert any(item.code == "naming_sql_param_mismatch" for item in result.issues)


def test_validator_warns_when_expected_signature_missing_fields() -> None:
    env = _env_with_naming_sql([{"param_name": "END_DATE", "is_list": False}])
    plan = ProgramPlan(
        definitions=[],
        return_expr=QueryCallPlanNode(
            type="query_call",
            query_kind="fetch_one",
            source_name="InvoiceBO",
            bo_id="bo:InvoiceBO",
            naming_sql_id="invoice_query_001",
            pairs=[QueryPairPlanNode(key="END_DATE", value=LiteralPlanNode(type="literal", value="2026-01-01"))],
        ),
    )

    result = PlanValidator().validate(plan, env)
    warnings = [item for item in result.issues if item.severity == "warning"]
    assert any(item.code == "naming_sql_param_signature_incomplete" for item in warnings)


def test_validator_type_check_uses_data_type_then_name_then_is_list() -> None:
    env = _env_with_naming_sql(
        [{"param_name": "END_DATE", "data_type": "basic", "data_type_name": "Date", "is_list": False}]
    )
    plan = ProgramPlan(
        definitions=[],
        return_expr=QueryCallPlanNode(
            type="query_call",
            query_kind="fetch_one",
            source_name="InvoiceBO",
            bo_id="bo:InvoiceBO",
            naming_sql_id="invoice_query_001",
            pairs=[
                QueryPairPlanNode(
                    key="END_DATE",
                    value=LiteralPlanNode(
                        type="literal",
                        value={"data_type": "basic", "data_type_name": "String", "is_list": False},
                    ),
                )
            ],
        ),
    )

    result = PlanValidator().validate(plan, env)
    assert any(item.code == "naming_sql_param_type_mismatch" for item in result.issues)
    assert any("data_type_name mismatch" in item.message for item in result.issues)
