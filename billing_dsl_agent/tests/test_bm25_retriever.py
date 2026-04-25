from billing_dsl_agent.models import ContextResource, FunctionResource
from billing_dsl_agent.resource_retrieval.bm25_retriever import BM25Retriever
from billing_dsl_agent.resource_retrieval.document_builder import ResourceDocumentBuilder


def test_bm25_recalls_bill_cycle_context() -> None:
    builder = ResourceDocumentBuilder()
    retriever = BM25Retriever()
    documents = builder.build_context_documents(
        [
            ContextResource(
                resource_id="context:$ctx$.billCycleId",
                name="billCycleId",
                path="$ctx$.billCycleId",
                description="账期标识",
                domain="billing",
            ),
            ContextResource(
                resource_id="context:$ctx$.customerId",
                name="customerId",
                path="$ctx$.customerId",
                description="客户标识",
                domain="customer",
            ),
        ]
    )
    retriever.build(documents)
    hits = retriever.search(["账期"], top_k=5)
    assert hits[0].resource_id == "context:$ctx$.billCycleId"


def test_bm25_recalls_currency_rate_resources() -> None:
    builder = ResourceDocumentBuilder()
    retriever = BM25Retriever()
    documents = [
        *builder.build_context_documents(
            [
                ContextResource(
                    resource_id="context:$ctx$.currencyRate",
                    name="currencyRate",
                    path="$ctx$.currencyRate",
                    description="汇率值",
                    domain="billing",
                )
            ]
        ),
        *builder.build_function_documents(
            [
                FunctionResource(
                    resource_id="function:Currency.GetRate",
                    function_id="function:Currency.GetRate",
                    name="GetRate",
                    full_name="Currency.GetRate",
                    description="查询汇率",
                    return_type="decimal",
                )
            ]
        ),
    ]
    retriever.build(documents)
    hits = retriever.search(["汇率"], top_k=5)
    assert {item.resource_id for item in hits} >= {"context:$ctx$.currencyRate", "function:Currency.GetRate"}
