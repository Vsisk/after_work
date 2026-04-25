from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.resource_retrieval.rrf_ranker import RRFRanker
from billing_dsl_agent.resource_retrieval.schemas import ResourceDocument, RetrievalHit


def test_rrf_prefers_dual_hit_resource() -> None:
    ranker = RRFRanker()
    documents = {
        "r1": ResourceDocument("r1", "context", "billCycleId", "账期", "账期 bill cycle id"),
        "r2": ResourceDocument("r2", "context", "cycleName", "周期名称", "周期"),
    }
    ranked = ranker.rank(
        resource_type="context",
        documents=documents,
        bm25_hits=[RetrievalHit("r1", "context", 3.0, 1, "bm25"), RetrievalHit("r2", "context", 2.0, 2, "bm25")],
        vector_hits=[RetrievalHit("r1", "context", 0.9, 2, "vector")],
        node_def=NodeDef(node_id="n1", node_path="invoice.billCycle", node_name="billCycle"),
        top_k=20,
    )
    assert ranked[0].resource_id == "r1"


def test_rrf_keeps_single_path_high_rank_resource() -> None:
    ranker = RRFRanker()
    documents = {
        "r1": ResourceDocument("r1", "function", "Currency.GetRate", "汇率查询", "currency get rate"),
        "r2": ResourceDocument("r2", "function", "Currency.Format", "格式化", "currency format"),
    }
    ranked = ranker.rank(
        resource_type="function",
        documents=documents,
        bm25_hits=[],
        vector_hits=[RetrievalHit("r1", "function", 0.95, 1, "vector"), RetrievalHit("r2", "function", 0.2, 2, "vector")],
        node_def=NodeDef(node_id="n1", node_path="invoice.rate", node_name="rate"),
        top_k=20,
    )
    assert any(item.resource_id == "r1" for item in ranked[:20])
