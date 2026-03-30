from pathlib import Path
from typing import Any

from pydantic import BaseModel

from billing_dsl_agent.services.llm_client import OpenAILLMClient, extract_param
from billing_dsl_agent.services.prompt_manager import PromptManager


def test_extract_param_filters_supported_reasoning_params() -> None:
    params = extract_param(
        {"temperature": 0.2, "top_k": 10, "top_n": 3, "ignored": "value"},
        max_output_tokens=512,
    )

    assert params == {
        "temperature": 0.2,
        "top_k": 10,
        "top_n": 3,
        "max_output_tokens": 512,
    }


def test_openai_llm_client_defaults_to_json_response_and_returns_dict(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text(
        '{"demo":{"zh":"需求：{{requirement}}","en":"Requirement: {{requirement}}"}}',
        encoding="utf-8",
    )
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                "OPENAI_BASE_URL=https://example.com/v1",
                "OPENAI_MODEL=gpt-4o-mini",
                "OPENAI_CHAT_COMPLETIONS_PATH=/chat/completions",
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"answer":"ok","lang":"zh"}',
                    }
                }
            ]
        }

    client = OpenAILLMClient(
        prompt_manager=PromptManager(prompt_path=prompt_path),
        env_path=env_path,
        transport=transport,
    )

    result = client.invoke(
        prompt_key="demo",
        lang="zh",
        prompt_params={"requirement": "输出一个 JSON"},
        top_k=8,
        top_n=2,
    )

    assert result == {"answer": "ok", "lang": "zh"}
    assert captured["url"].endswith("/chat/completions")
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["top_k"] == 8
    assert captured["payload"]["top_n"] == 2
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_openai_llm_client_supports_custom_response_format(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text('{"demo":{"en":"Hello {{name}}"}}', encoding="utf-8")
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")

    captured: dict[str, Any] = {}

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": "plain text result",
                    }
                }
            ]
        }

    client = OpenAILLMClient(
        prompt_manager=PromptManager(prompt_path=prompt_path),
        env_path=env_path,
        transport=transport,
    )

    result = client.invoke(
        prompt_key="demo",
        lang="en",
        prompt_params={"name": "OpenAI"},
        response_format="text",
        temperature=0.3,
    )

    assert result == {"result": "plain text result"}
    assert captured["payload"]["response_format"] == {"type": "text"}
    assert captured["payload"]["temperature"] == 0.3


class _SelectionModel(BaseModel):
    resource_id_list: list[str]


def test_openai_llm_client_structured_reports_prompt_render_error(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"query={{query}}","en":"query={{query}}"}}',
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")
    client = OpenAILLMClient(prompt_manager=PromptManager(prompt_path=prompt_path), env_path=env_path)

    result = client.execute_structured(
        prompt_key="semantic_selector_prompt",
        prompt_params={},
        response_model=_SelectionModel,
        stage="semantic_select",
        lang="zh",
    )

    assert result.parsed is None
    assert result.errors[0].code == "prompt_render_error"


def test_openai_llm_client_structured_reports_request_error(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"query={{query}}","en":"query={{query}}"}}',
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        raise RuntimeError("boom")

    client = OpenAILLMClient(
        prompt_manager=PromptManager(prompt_path=prompt_path),
        env_path=env_path,
        transport=transport,
    )

    result = client.execute_structured(
        prompt_key="semantic_selector_prompt",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
        lang="zh",
    )

    assert result.parsed is None
    assert result.errors[0].code == "llm_request_error"


def test_openai_llm_client_structured_reports_non_json_output(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"query={{query}}","en":"query={{query}}"}}',
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "plain text"}}]}

    client = OpenAILLMClient(
        prompt_manager=PromptManager(prompt_path=prompt_path),
        env_path=env_path,
        transport=transport,
    )

    result = client.execute_structured(
        prompt_key="semantic_selector_prompt",
        lang="zh",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is None
    assert result.errors[0].code == "response_not_json"


def test_openai_llm_client_structured_reports_schema_error(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"query={{query}}","en":"query={{query}}"}}',
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        return {"choices": [{"message": {"content": '{"wrong_key": []}'}}]}

    client = OpenAILLMClient(
        prompt_manager=PromptManager(prompt_path=prompt_path),
        env_path=env_path,
        transport=transport,
    )

    result = client.execute_structured(
        prompt_key="semantic_selector_prompt",
        lang="zh",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is None
    assert result.errors[0].code == "response_schema_error"


def test_openai_llm_client_structured_uses_json_schema_response_format(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text(
        '{"semantic_selector_prompt":{"zh":"query={{query}}","en":"query={{query}}"}}',
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")
    captured: dict[str, Any] = {}

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"resource_id_list":["ctx_001"]}'}}]}

    client = OpenAILLMClient(
        prompt_manager=PromptManager(prompt_path=prompt_path),
        env_path=env_path,
        transport=transport,
    )

    result = client.execute_structured(
        prompt_key="semantic_selector_prompt",
        lang="zh",
        prompt_params={"query": "hello"},
        response_model=_SelectionModel,
        stage="semantic_select",
    )

    assert result.parsed is not None
    assert captured["payload"]["response_format"]["type"] == "json_schema"


def test_openai_llm_client_uses_llm_name_config_from_env(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text('{"demo":{"zh":"需求：{{requirement}}"}}', encoding="utf-8")
    env_path.write_text(
        "\n".join(
            [
                "LLM_DEFAULT_NAME=text_default",
                "LLM_TEXT_DEFAULT_API_KEY=test-key",
                "LLM_TEXT_DEFAULT_BASE_URL=https://example.com/v1",
                "LLM_TEXT_DEFAULT_MODEL=gpt-4.1-mini",
                "LLM_TEXT_DEFAULT_CHAT_COMPLETIONS_PATH=/chat/completions",
                "LLM_TEXT_DEFAULT_TIMEOUT=12",
            ]
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {"choices": [{"message": {"content": '{"answer":"ok"}'}}]}

    client = OpenAILLMClient(prompt_manager=PromptManager(prompt_path=prompt_path), env_path=env_path, transport=transport)
    result = client.invoke(prompt_key="demo", lang="zh", prompt_params={"requirement": "x"})
    assert result == {"answer": "ok"}
    assert captured["payload"]["model"] == "gpt-4.1-mini"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["timeout"] == 12.0


def test_openai_llm_client_supports_multimodal_url_and_path(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    image_path = tmp_path / "demo.png"
    prompt_path.write_text('{"demo":{"zh":"识别图像"}}', encoding="utf-8")
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")
    image_path.write_bytes(b"fakepng")
    captured: dict[str, Any] = {}

    def transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"answer":"ok"}'}}]}

    client = OpenAILLMClient(prompt_manager=PromptManager(prompt_path=prompt_path), env_path=env_path, transport=transport)
    result = client.invoke_multimodal(
        prompt_key="demo",
        lang="zh",
        image_urls=["https://example.com/a.png"],
        image_paths=[str(image_path)],
    )
    assert result == {"answer": "ok"}
    content = captured["payload"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"] == "https://example.com/a.png"
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openai_llm_client_multimodal_requires_images(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    env_path = tmp_path / ".env"
    prompt_path.write_text('{"demo":{"zh":"识别图像"}}', encoding="utf-8")
    env_path.write_text("OPENAI_API_KEY=test-key", encoding="utf-8")
    client = OpenAILLMClient(prompt_manager=PromptManager(prompt_path=prompt_path), env_path=env_path)
    try:
        client.invoke_multimodal(prompt_key="demo", lang="zh")
        assert False, "should raise"
    except Exception as exc:
        assert "invalid_image_input" in str(exc)
