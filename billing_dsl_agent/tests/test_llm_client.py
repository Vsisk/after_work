from pathlib import Path
from typing import Any

from billing_dsl_agent.services.llm_client import OpenAILLMClient, extract_param
from billing_dsl_agent.services.llm_service import PromptDrivenLLMService
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
    assert captured["url"] == "https://example.com/v1/chat/completions"
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

    service = PromptDrivenLLMService(
        client=OpenAILLMClient(
            prompt_manager=PromptManager(prompt_path=prompt_path),
            env_path=env_path,
            transport=transport,
        )
    )

    result = service.generate(
        prompt_key="demo",
        lang="en",
        prompt_params={"name": "OpenAI"},
        response_format="text",
        temperature=0.3,
    )

    assert result == {"result": "plain text result"}
    assert captured["payload"]["response_format"] == {"type": "text"}
    assert captured["payload"]["temperature"] == 0.3
