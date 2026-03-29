from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from billing_dsl_agent.services.prompt_manager import PromptManager
from billing_dsl_agent.services.structured_llm_executor import StructuredLLMExecutor


class _SelectionModel(BaseModel):
    resource_id_list: list[str]


@dataclass(slots=True)
class _RawResponse:
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]


@dataclass(slots=True)
class _PromptClient:
    response_payload: dict[str, Any] | None = None
    raise_error: Exception | None = None
    last_response_format: dict[str, Any] | None = None

    def generate_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: dict[str, Any] | None = None,
        response_format: dict[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> _RawResponse:
        if self.raise_error is not None:
            raise self.raise_error
        self.last_response_format = response_format if isinstance(response_format, dict) else {"type": response_format}
        return _RawResponse(
            request_payload={
                "prompt_key": prompt_key,
                "lang": lang,
                "prompt_params": dict(prompt_params or {}),
                "response_format": response_format,
            },
            response_payload=dict(self.response_payload or {}),
        )


@dataclass(slots=True)
class _LegacyClient:
    last_payload: dict[str, Any] | None = None

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_payload = payload
        return {"resource_id_list": ["ctx_001"]}


def _prompt_manager(tmp_path: Path) -> PromptManager:
    prompt_path = tmp_path / "prompt.json"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"query={{query}}","en":"query={{query}}"}}',
        encoding="utf-8",
    )
    return PromptManager(prompt_path=prompt_path)


def test_structured_executor_reports_prompt_render_error(tmp_path: Path) -> None:
    executor = StructuredLLMExecutor(client=_LegacyClient(), prompt_manager=_prompt_manager(tmp_path), default_lang="zh")
    result = executor.execute(
        prompt_key="semantic_selector_prompt",
        prompt_params={},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is None
    assert result.errors[0].code == "prompt_render_error"


def test_structured_executor_reports_request_error(tmp_path: Path) -> None:
    executor = StructuredLLMExecutor(
        client=_PromptClient(raise_error=RuntimeError("boom")),
        prompt_manager=_prompt_manager(tmp_path),
        default_lang="zh",
    )
    result = executor.execute(
        prompt_key="semantic_selector_prompt",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is None
    assert result.errors[0].code == "llm_request_error"


def test_structured_executor_reports_non_json_output(tmp_path: Path) -> None:
    executor = StructuredLLMExecutor(
        client=_PromptClient(response_payload={"choices": [{"message": {"content": "plain text"}}]}),
        prompt_manager=_prompt_manager(tmp_path),
        default_lang="zh",
    )
    result = executor.execute(
        prompt_key="semantic_selector_prompt",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is None
    assert result.errors[0].code == "response_not_json"


def test_structured_executor_reports_schema_error(tmp_path: Path) -> None:
    executor = StructuredLLMExecutor(
        client=_PromptClient(response_payload={"choices": [{"message": {"content": '{"wrong_key": []}'}}]}),
        prompt_manager=_prompt_manager(tmp_path),
        default_lang="zh",
    )
    result = executor.execute(
        prompt_key="semantic_selector_prompt",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is None
    assert result.errors[0].code == "response_schema_error"


def test_structured_executor_uses_json_schema_response_format(tmp_path: Path) -> None:
    client = _PromptClient(response_payload={"choices": [{"message": {"content": '{"resource_id_list":["ctx_001"]}'}}]})
    executor = StructuredLLMExecutor(client=client, prompt_manager=_prompt_manager(tmp_path), default_lang="zh")
    result = executor.execute(
        prompt_key="semantic_selector_prompt",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is not None
    assert client.last_response_format is not None
    assert client.last_response_format["type"] == "json_schema"


def test_structured_executor_falls_back_to_json_object_without_response_model(tmp_path: Path) -> None:
    client = _PromptClient(response_payload={"choices": [{"message": {"content": '{"resource_id_list":["ctx_001"]}'}}]})
    executor = StructuredLLMExecutor(client=client, prompt_manager=_prompt_manager(tmp_path), default_lang="zh")
    result = executor.execute(
        prompt_key="semantic_selector_prompt",
        prompt_params={"query": "hello"},
        response_model=None,
        response_parser=lambda payload: _SelectionModel.model_validate(payload),
        stage="semantic_select",
    )

    assert result.parsed is not None
    assert client.last_response_format == {"type": "json_object"}
