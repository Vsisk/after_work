from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from billing_dsl_agent.models import LLMAttemptRecord
from billing_dsl_agent.services.llm_client import StructuredExecutionResult
from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.services.prompt_manager import PromptManager
from billing_dsl_agent.semantic_selector import CandidateSummary, OpenAISemanticSelector


@dataclass(slots=True)
class _StubSelectorClient:
    response: Optional[Dict[str, Any]]
    last_payload: Optional[Dict[str, Any]] = None
    prompt_manager: PromptManager | None = None

    def execute_structured(
        self,
        *,
        prompt_key: str,
        lang: str,
        prompt_params: Dict[str, Any] | None,
        response_model: Any,
        stage: str,
        attempt_index: int = 1,
        response_parser: Any = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[Any]:
        self.last_payload = dict(prompt_params or {})
        parsed = response_model.model_validate(self.response) if self.response else None
        return StructuredExecutionResult(
            parsed=parsed,
            errors=[],
            raw_payload=self.response,
            attempt=LLMAttemptRecord(
                stage=stage,
                attempt_index=attempt_index,
                request_payload=self.last_payload,
                response_payload=self.response,
                parsed_ok=parsed is not None,
                errors=[],
            ),
        )


def _node() -> NodeDef:
    return NodeDef(
        node_id="n_001",
        node_name="beginDate",
        node_path="$.mapping_content.children[0].children[1]",
        description="bill begin date",
    )


def _candidates() -> list[CandidateSummary]:
    return [
        CandidateSummary(resource_id="ctx_001", description="$ctx$.bill.cycleType bill cycle type", tags=["context"]),
        CandidateSummary(
            resource_id="ctx_002",
            description="$ctx$.bill.beginDate current bill begin date",
            tags=["context"],
        ),
        CandidateSummary(resource_id="ctx_003", description="$ctx$.bill.clearDate bill clear date", tags=["context"]),
    ]


def test_openai_semantic_selector_builds_expected_payload(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"task={{task_type}} user={{user_query}} node={{node_def_json}} candidates={{candidate_list_json}} max={{max_items}}"}}',
        encoding="utf-8",
    )

    client = _StubSelectorClient(response={"resource_id_list": ["ctx_002", "ctx_003"]})
    selector = OpenAISemanticSelector(
        client=client,
        default_top_k=5,
    )
    selector.client.prompt_manager = PromptManager(prompt_path=prompt_path)

    selected = selector.select(
        task_type="context",
        node_info=_node(),
        user_query="if cycle type is prepaid, return current bill begin date, else return clear date",
        candidate_summaries=_candidates(),
    )

    assert selected == ["ctx_002", "ctx_003"]
    assert client.last_payload is not None
    assert client.last_payload["user_query"] == (
        "if cycle type is prepaid, return current bill begin date, else return clear date"
    )
    assert client.last_payload["task_type"] == "context"


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
