from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    FunctionParamResource,
    FunctionResource,
    NormalizedNamingSQLDef,
    NormalizedNamingSQLParam,
)
from billing_dsl_agent.resource_retrieval.document_builder import ResourceDocumentBuilder


def test_context_resource_builds_search_text() -> None:
    builder = ResourceDocumentBuilder()
    document = builder.build_context_document(
        ContextResource(
            resource_id="context:$ctx$.billCycleId",
            name="billCycleId",
            path="$ctx$.billCycleId",
            domain="billing",
            description="账期标识",
            tags=["cycle"],
        )
    )
    assert "bill cycle id" in document.search_text
    assert "账期标识" in document.search_text
    assert "billing" in document.search_text


def test_bo_resource_builds_search_text() -> None:
    builder = ResourceDocumentBuilder()
    document = builder.build_bo_document(
        BOResource(
            resource_id="bo:BillBO",
            bo_name="BillBO",
            field_ids=["billCycleId", "customerId"],
            naming_sql_ids=["query_bill_cycle"],
            naming_sqls=[
                NormalizedNamingSQLDef(
                    naming_sql_id="query_bill_cycle",
                    naming_sql_name="QUERY_BILL_CYCLE",
                    bo_id="bo:BillBO",
                    description="按账期查询",
                    params=[
                        NormalizedNamingSQLParam(param_id="p1", param_name="billCycleId", data_type_name="LONG")
                    ],
                )
            ],
            description="账单业务对象",
            domain="billing",
        )
    )
    assert "billbo" in document.search_text
    assert "bill cycle id" in document.search_text
    assert "query bill cycle" in document.search_text


def test_function_resource_builds_search_text() -> None:
    builder = ResourceDocumentBuilder()
    document = builder.build_function_document(
        FunctionResource(
            resource_id="function:Currency.GetRate",
            function_id="function:Currency.GetRate",
            name="GetRate",
            full_name="Currency.GetRate",
            description="查询汇率",
            params=["sourceCurrency", "targetCurrency"],
            param_defs=[
                FunctionParamResource(param_id="p1", param_name="sourceCurrency"),
                FunctionParamResource(param_id="p2", param_name="targetCurrency"),
            ],
            return_type="decimal",
            tags=["currency"],
        )
    )
    assert "currency get rate" in document.search_text
    assert "查询汇率" in document.search_text
    assert "source currency" in document.search_text
    assert "decimal" in document.search_text
