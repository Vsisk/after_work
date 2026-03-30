from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generic, Mapping, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from billing_dsl_agent.models import LLMErrorRecord, LLMAttemptRecord
from billing_dsl_agent.services.llm_post_processor import extract_response_text
from billing_dsl_agent.services.llm_post_processor import post_process_response
from billing_dsl_agent.services.prompt_manager import PromptManager, PromptManagerError

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
ModelT = TypeVar("ModelT")


@dataclass(slots=True)
class RawLLMInvocation:
    request_url: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]


@dataclass(slots=True)
class StructuredExecutionResult(Generic[ModelT]):
    parsed: ModelT | None
    errors: list[LLMErrorRecord]
    attempt: LLMAttemptRecord
    raw_text: str = ""
    raw_payload: dict[str, Any] | None = None


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

    def execute_structured(
        self,
        *,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None,
        response_model: type[BaseModel] | None,
        stage: str,
        attempt_index: int = 1,
        response_parser: Callable[[dict[str, Any]], ModelT] | None = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[ModelT]:
        request_payload: dict[str, Any] | None = None
        response_payload: dict[str, Any] | None = None
        raw_text = ""
        errors: list[LLMErrorRecord] = []
        response_format = self._build_response_format(response_model)

        try:
            raw_invocation = self.invoke_raw(
                prompt_key=prompt_key,
                lang=lang,
                prompt_params=prompt_params,
                response_format=response_format,
                **kwargs,
            )
            request_payload = self._as_dict(getattr(raw_invocation, "request_payload", None))
            response_payload = self._as_dict(getattr(raw_invocation, "response_payload", None))
        except PromptManagerError as exc:
            errors.append(
                self._error(
                    stage=stage,
                    code="prompt_render_error",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    raw_payload=request_payload,
                )
            )
            return self._result(None, errors, stage, attempt_index, request_payload, response_payload)
        except Exception as exc:
            errors.append(
                self._error(
                    stage=stage,
                    code="llm_request_error",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                    raw_payload=request_payload,
                )
            )
            return self._result(None, errors, stage, attempt_index, request_payload, response_payload)

        if not response_payload:
            errors.append(
                self._error(
                    stage=stage,
                    code="empty_response",
                    message="llm returned no response payload",
                    raw_payload=request_payload,
                )
            )
            return self._result(None, errors, stage, attempt_index, request_payload, response_payload)

        raw_text = extract_response_text(response_payload)
        parsed_payload: dict[str, Any] | None = None
        if raw_text:
            try:
                loaded = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                errors.append(
                    self._error(
                        stage=stage,
                        code="response_not_json",
                        message=f"llm output is not valid json: {exc}",
                        raw_text=raw_text,
                        raw_payload=response_payload,
                        exception_type=type(exc).__name__,
                    )
                )
                return self._result(None, errors, stage, attempt_index, request_payload, response_payload, raw_text)
            if not isinstance(loaded, dict):
                errors.append(
                    self._error(
                        stage=stage,
                        code="response_root_not_object",
                        message="llm output root must be a json object",
                        raw_text=raw_text,
                        raw_payload={"result": loaded},
                    )
                )
                return self._result(None, errors, stage, attempt_index, request_payload, response_payload, raw_text)
            parsed_payload = loaded
        else:
            content = response_payload.get("content")
            if isinstance(content, dict):
                parsed_payload = dict(content)
            elif self._looks_like_payload_object(response_payload):
                parsed_payload = dict(response_payload)

        if parsed_payload is None:
            errors.append(
                self._error(
                    stage=stage,
                    code="empty_response_text",
                    message="llm response did not contain parseable text or object payload",
                    raw_payload=response_payload,
                )
            )
            return self._result(None, errors, stage, attempt_index, request_payload, response_payload, raw_text)

        try:
            if response_parser is not None:
                parsed = response_parser(parsed_payload)
            elif response_model is not None:
                parsed = response_model.model_validate(parsed_payload)
            else:
                raise TypeError("response_model or response_parser is required")
        except (ValidationError, ValueError, TypeError) as exc:
            errors.append(
                self._error(
                    stage=stage,
                    code="response_schema_error",
                    message=str(exc),
                    raw_text=raw_text,
                    raw_payload=parsed_payload,
                    exception_type=type(exc).__name__,
                )
            )
            return self._result(None, errors, stage, attempt_index, request_payload, response_payload, raw_text)

        return self._result(parsed, errors, stage, attempt_index, request_payload, response_payload, raw_text)

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

    def _build_response_format(self, response_model: type[BaseModel] | None) -> dict[str, Any]:
        if response_model is None:
            return {"type": "json_object"}
        try:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                },
            }
        except Exception:
            return {"type": "json_object"}

    def _looks_like_payload_object(self, payload: Mapping[str, Any]) -> bool:
        if "choices" in payload or "output" in payload or "output_text" in payload:
            return False
        return True

    def _result(
        self,
        parsed: ModelT | None,
        errors: list[LLMErrorRecord],
        stage: str,
        attempt_index: int,
        request_payload: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
        raw_text: str = "",
    ) -> StructuredExecutionResult[ModelT]:
        return StructuredExecutionResult(
            parsed=parsed,
            errors=list(errors),
            raw_text=raw_text,
            raw_payload=response_payload,
            attempt=LLMAttemptRecord(
                stage=stage,
                attempt_index=attempt_index,
                request_payload=request_payload,
                response_payload=response_payload,
                parsed_ok=parsed is not None and not errors,
                errors=list(errors),
            ),
        )

    def _error(
        self,
        *,
        stage: str,
        code: str,
        message: str,
        raw_text: str = "",
        raw_payload: dict[str, Any] | None = None,
        exception_type: str = "",
    ) -> LLMErrorRecord:
        return LLMErrorRecord(
            stage=stage,
            code=code,
            message=message,
            raw_text=raw_text,
            raw_payload=raw_payload,
            exception_type=exception_type,
        )

    def _as_dict(self, payload: Any) -> dict[str, Any] | None:
        if payload is None:
            return None
        if isinstance(payload, dict):
            return dict(payload)
        return {"result": payload}
