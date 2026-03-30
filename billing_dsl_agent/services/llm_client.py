from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from billing_dsl_agent.services.llm_post_processor import post_process_response
from billing_dsl_agent.services.prompt_manager import PromptManager

_DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_DEFAULT_TIMEOUT = 60.0
_SUPPORTED_MODEL_PARAMS = {
    "frequency_penalty",
    "max_completion_tokens",
    "max_output_tokens",
    "metadata",
    "n",
    "parallel_tool_calls",
    "presence_penalty",
    "reasoning_effort",
    "seed",
    "stop",
    "store",
    "temperature",
    "tool_choice",
    "tools",
    "top_k",
    "top_n",
    "top_p",
    "user",
}


class LLMClientError(RuntimeError):
    """Raised when the OpenAI client cannot complete a request."""


Transport = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]


@dataclass(slots=True)
class RawLLMInvocation:
    request_url: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]


def _load_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def extract_param(params: Mapping[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if params:
        merged.update(dict(params))
    merged.update(kwargs)

    extracted: dict[str, Any] = {}
    for key, value in merged.items():
        if key in _SUPPORTED_MODEL_PARAMS and value is not None:
            extracted[key] = value
    return extracted


def _normalize_response_format(response_format: Mapping[str, Any] | str | None) -> dict[str, Any]:
    if response_format is None:
        return {"type": "json_object"}
    if isinstance(response_format, str):
        return {"type": response_format}
    return dict(response_format)


def _default_transport(
    request_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        url=request_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"openai request failed with status {exc.code}: {detail}") from exc
    except URLError as exc:
        raise LLMClientError(f"openai request failed: {exc.reason}") from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMClientError("openai response is not valid JSON") from exc

    if not isinstance(decoded, dict):
        raise LLMClientError("openai response root must be a JSON object")
    return decoded


@dataclass(slots=True)
class OpenAILLMClient:
    prompt_manager: PromptManager = field(default_factory=PromptManager)
    env_path: Path = _DEFAULT_ENV_PATH
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout: float = _DEFAULT_TIMEOUT
    transport: Transport = _default_transport

    def invoke(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raw_invocation = self.invoke_raw(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            response_format=response_format,
            **kwargs,
        )
        return post_process_response(raw_invocation.response_payload)


    # Backward-compatible aliases to align with StructuredLLMExecutor client protocol.
    def generate(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.invoke(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            response_format=response_format,
            **kwargs,
        )

    def generate_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> RawLLMInvocation:
        return self.invoke_raw(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            response_format=response_format,
            **kwargs,
        )
    def invoke_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> RawLLMInvocation:
        prompt = self.prompt_manager.render_prompt(prompt_key, lang, prompt_params)
        payload = self._build_payload(prompt=prompt, response_format=response_format, extra_params=kwargs)
        request_url = self._resolve_request_url()
        raw_response = self.transport(
            request_url,
            payload,
            self._build_headers(),
            self._resolve_timeout(),
        )
        return RawLLMInvocation(
            request_url=request_url,
            request_payload=payload,
            response_payload=raw_response,
        )

    def _build_payload(
        self,
        prompt: str,
        response_format: Mapping[str, Any] | str | None,
        extra_params: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._resolve_model(),
            "messages": [{"role": "user", "content": prompt}],
            "response_format": _normalize_response_format(response_format),
        }
        payload.update(extract_param(extra_params))
        return payload

    def _resolve_request_url(self) -> str:
        base_url = self.base_url or os.getenv("OPENAI_BASE_URL") or self._load_env().get("OPENAI_BASE_URL")
        normalized_base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        path = os.getenv("OPENAI_CHAT_COMPLETIONS_PATH") or self._load_env().get("OPENAI_CHAT_COMPLETIONS_PATH")
        normalized_path = path or "/chat/completions"
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        return f"{normalized_base_url}{normalized_path}"

    def _build_headers(self) -> dict[str, str]:
        api_key = self.api_key or os.getenv("OPENAI_API_KEY") or self._load_env().get("OPENAI_API_KEY")
        if not api_key:
            raise LLMClientError("OPENAI_API_KEY is not configured in environment or .env")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _resolve_model(self) -> str:
        model = self.model or os.getenv("OPENAI_MODEL") or self._load_env().get("OPENAI_MODEL")
        return model or "gpt-4o-mini"

    def _resolve_timeout(self) -> float:
        timeout = os.getenv("OPENAI_TIMEOUT") or self._load_env().get("OPENAI_TIMEOUT")
        if timeout:
            try:
                return float(timeout)
            except ValueError:
                raise LLMClientError("OPENAI_TIMEOUT must be a number") from None
        return self.timeout

    def _load_env(self) -> dict[str, str]:
        return _load_env_file(self.env_path)
