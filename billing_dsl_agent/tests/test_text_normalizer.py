from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.resource_retrieval.concept_extractor import ConceptExtractor
from billing_dsl_agent.resource_retrieval.text_normalizer import TextNormalizer


def test_bill_cycle_identifier_is_split() -> None:
    normalizer = TextNormalizer()
    expanded = normalizer.expand_text("billCycleId")
    assert "billcycleid" in expanded
    assert "bill cycle id" in expanded


def test_currency_rate_identifier_is_split() -> None:
    normalizer = TextNormalizer()
    expanded = normalizer.expand_text("CURRENCY_RATE")
    assert "currency_rate" in expanded
    assert "currency rate" in expanded


def test_chinese_terms_are_detected_from_dictionary() -> None:
    extractor = ConceptExtractor()
    concepts = extractor.extract(
        user_query="根据账期计算汇率",
        node_def=NodeDef(node_id="n1", node_path="invoice.amount", node_name="amount", description="账期汇率字段"),
    )
    assert "账期" in concepts.domain_terms
    assert "汇率" in concepts.domain_terms
    assert any(item in concepts.keywords for item in ["账期", "汇率"])
