from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.semantic_selector import CandidateSummary, OpenAISemanticSelector


@dataclass(slots=True)
class _StubSelectorClient:
    response: Optional[Dict[str, Any]]
    last_payload: Optional[Dict[str, Any]] = None

    def create_plan(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.last_payload = payload
        return self.response


def _node() -> NodeDef:
    return NodeDef(
        node_id="n_001",
        node_name="beginDate",
        node_path="$.mapping_content.children[0].children[1]",
        description="账单开始时间",
    )


def _candidates() -> list[CandidateSummary]:
    return [
        CandidateSummary(resource_id="ctx_001", description="$ctx$.bill.cycleType 账期类型", tags=["context"]),
        CandidateSummary(resource_id="ctx_002", description="$ctx$.bill.beginDate 当前账期开始时间", tags=["context"]),
        CandidateSummary(resource_id="ctx_003", description="$ctx$.bill.clearDate 销账时间", tags=["context"]),
    ]


def test_openai_semantic_selector_builds_expected_payload(tmp_path: Path) -> None:
    prompt_path = tmp_path / "semantic_selector_prompt.json"
    prompt_path.write_text('{"system":"sys","instruction":"inst"}', encoding="utf-8")

    client = _StubSelectorClient(response={"resource_id_list": ["ctx_002", "ctx_003"]})
    selector = OpenAISemanticSelector(client=client, prompt_path=prompt_path, default_top_k=5)

    selected = selector.select(
        task_type="context",
        node_info=_node(),
        user_query="如果账期类型为预付，则返回当前账期开始时间，否则返回销账时间",
        candidate_summaries=_candidates(),
    )

    assert selected == ["ctx_002", "ctx_003"]
    assert client.last_payload is not None
    assert client.last_payload["mode"] == "semantic_select"
    assert client.last_payload["input"]["user_query"] == "如果账期类型为预付，则返回当前账期开始时间，否则返回销账时间"


def test_openai_semantic_selector_filters_unknown_ids() -> None:
    client = _StubSelectorClient(response={"resource_id_list": ["ctx_002", "ctx_999", "ctx_001"]})
    selector = OpenAISemanticSelector(client=client)

    selected = selector.select(
        task_type="context",
        node_info=_node(),
        user_query="test",
        candidate_summaries=_candidates(),
    )

    assert selected == ["ctx_002", "ctx_001"]
