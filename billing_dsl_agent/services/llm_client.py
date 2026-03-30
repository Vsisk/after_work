from __future__ import annotations

import json
import os
import base64
import mimetypes
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generic, Mapping, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from billing_dsl_agent.log_utils import dumps_for_log, get_logger
from billing_dsl_agent.models import LLMErrorRecord, LLMAttemptRecord
from billing_dsl_agent.services.llm_post_processor import extract_response_text
from billing_dsl_agent.services.llm_post_processor import post_process_response
from billing_dsl_agent.services.prompt_manager import PromptManager, PromptManagerError

logger = get_logger(__name__)

_DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_DEFAULT_TIMEOUT = 600.0
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


@dataclass(slots=True)
class LLMConfig:
    name: str
    model: str
    api_key: str
    base_url: str
    chat_completions_path: str
    timeout: float


class BaseOpenAILLMClient(ABC):
    env_path: Path
    api_key: str | None
    base_url: str | None
    model: str | None
    timeout: float

    @abstractmethod
    def _load_env(self) -> dict[str, str]:
        raise NotImplementedError

    def resolve_config(self, llm_name: str | None = None) -> LLMConfig:
        env = self._load_env()
        effective_name = llm_name or os.getenv("LLM_DEFAULT_NAME") or env.get("LLM_DEFAULT_NAME") or "default"
        normalized_name = effective_name.upper().replace("-", "_")
        model = self.model or os.getenv(f"LLM_{normalized_name}_MODEL") or env.get(f"LLM_{normalized_name}_MODEL")
        if not model:
            model = os.getenv("OPENAI_MODEL") or env.get("OPENAI_MODEL") or "gpt-4o-mini"

        api_key = self.api_key or os.getenv(f"LLM_{normalized_name}_API_KEY") or env.get(f"LLM_{normalized_name}_API_KEY")
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMClientError(f"llm config not found for name={effective_name!r}: api key is missing")

        base_url = self.base_url or os.getenv(f"LLM_{normalized_name}_BASE_URL") or env.get(f"LLM_{normalized_name}_BASE_URL")
        if not base_url:
            base_url = os.getenv("OPENAI_BASE_URL") or env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"

        path = os.getenv(f"LLM_{normalized_name}_CHAT_COMPLETIONS_PATH") or env.get(
            f"LLM_{normalized_name}_CHAT_COMPLETIONS_PATH"
        )
        if not path:
            path = os.getenv("OPENAI_CHAT_COMPLETIONS_PATH") or env.get("OPENAI_CHAT_COMPLETIONS_PATH") or "/chat/completions"

        timeout_raw = os.getenv(f"LLM_{normalized_name}_TIMEOUT") or env.get(f"LLM_{normalized_name}_TIMEOUT")
        if not timeout_raw:
            timeout_raw = os.getenv("OPENAI_TIMEOUT") or env.get("OPENAI_TIMEOUT")
        if timeout_raw:
            try:
                timeout = float(timeout_raw)
            except ValueError:
                raise LLMClientError(f"timeout for llm {effective_name!r} must be a number") from None
        else:
            timeout = self.timeout

        return LLMConfig(
            name=effective_name,
            model=model,
            api_key=api_key,
            base_url=base_url,
            chat_completions_path=path,
            timeout=timeout,
        )


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
class OpenAILLMClient(BaseOpenAILLMClient):
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
        llm_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raw_invocation = self.invoke_raw(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            response_format=response_format,
            llm_name=llm_name,
            **kwargs,
        )
        return post_process_response(raw_invocation.response_payload)


    def invoke_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        llm_name: str | None = None,
        **kwargs: Any,
    ) -> RawLLMInvocation:
        config = self.resolve_config(llm_name=llm_name)
        prompt = self.prompt_manager.render_prompt(prompt_key, lang, prompt_params)
        payload = self._build_payload(prompt=prompt, response_format=response_format, extra_params=kwargs, model=config.model)
        request_url = self._resolve_request_url(config)
        logger.info(
            "llm_request_started llm_name=%s model=%s prompt_key=%s lang=%s request_url=%s payload=%s",
            config.name,
            config.model,
            prompt_key,
            lang,
            request_url,
            dumps_for_log(payload),
        )
        started_at = time.perf_counter()
        raw_response = self.transport(
            request_url,
            payload,
            self._build_headers(config),
            config.timeout,
        )
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "llm_request_completed llm_name=%s model=%s prompt_key=%s duration_ms=%s response=%s",
            config.name,
            config.model,
            prompt_key,
            duration_ms,
            dumps_for_log(raw_response),
        )
        return RawLLMInvocation(
            request_url=request_url,
            request_payload=payload,
            response_payload=raw_response,
        )

    def invoke_multimodal(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        image_urls: list[str] | None = None,
        image_paths: list[str] | None = None,
        llm_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raw = self.invoke_multimodal_raw(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            image_urls=image_urls,
            image_paths=image_paths,
            llm_name=llm_name,
            **kwargs,
        )
        return post_process_response(raw.response_payload)

    def invoke_multimodal_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        image_urls: list[str] | None = None,
        image_paths: list[str] | None = None,
        llm_name: str | None = None,
        **kwargs: Any,
    ) -> RawLLMInvocation:
        config = self.resolve_config(llm_name=llm_name)
        prompt = self.prompt_manager.render_prompt(prompt_key, lang, prompt_params)
        content = self._build_multimodal_content(prompt=prompt, image_urls=image_urls, image_paths=image_paths)
        payload = {"model": config.model, "messages": [{"role": "user", "content": content}]}
        payload.update(extract_param(kwargs))
        request_url = self._resolve_request_url(config)
        logger.info(
            "llm_multimodal_request_started llm_name=%s model=%s prompt_key=%s lang=%s request_url=%s payload=%s",
            config.name,
            config.model,
            prompt_key,
            lang,
            request_url,
            dumps_for_log(payload),
        )
        started_at = time.perf_counter()
        raw_response = self.transport(
            request_url,
            payload,
            self._build_headers(config),
            config.timeout,
        )
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "llm_multimodal_request_completed llm_name=%s model=%s prompt_key=%s duration_ms=%s response=%s",
            config.name,
            config.model,
            prompt_key,
            duration_ms,
            dumps_for_log(raw_response),
        )
        return RawLLMInvocation(request_url=request_url, request_payload=payload, response_payload=raw_response)

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
        llm_name: str | None = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[ModelT]:
        request_payload: dict[str, Any] | None = None
        response_payload: dict[str, Any] | None = None
        raw_text = ""
        errors: list[LLMErrorRecord] = []
        response_format = self._build_response_format(response_model)
        logger.info(
            "structured_llm_execution_started stage=%s attempt=%s prompt_key=%s",
            stage,
            attempt_index,
            prompt_key,
        )

        try:
            raw_invocation = self.invoke_raw(
                prompt_key=prompt_key,
                lang=lang,
                prompt_params=prompt_params,
                response_format=response_format,
                llm_name=llm_name,
                **kwargs,
            )
            request_payload = self._as_dict(getattr(raw_invocation, "request_payload", None))
            response_payload = self._as_dict(getattr(raw_invocation, "response_payload", None))
        except PromptManagerError as exc:
            logger.exception(
                "structured_llm_execution_failed stage=%s attempt=%s code=prompt_render_error",
                stage,
                attempt_index,
            )
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
            logger.exception(
                "structured_llm_execution_failed stage=%s attempt=%s code=llm_request_error",
                stage,
                attempt_index,
            )
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
            logger.warning(
                "structured_llm_execution_failed stage=%s attempt=%s code=empty_response",
                stage,
                attempt_index,
            )
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
                logger.warning(
                    "structured_llm_execution_failed stage=%s attempt=%s code=response_not_json raw_text=%s",
                    stage,
                    attempt_index,
                    raw_text,
                )
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
                logger.warning(
                    "structured_llm_execution_failed stage=%s attempt=%s code=response_root_not_object",
                    stage,
                    attempt_index,
                )
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
            logger.warning(
                "structured_llm_execution_failed stage=%s attempt=%s code=empty_response_text response=%s",
                stage,
                attempt_index,
                dumps_for_log(response_payload),
            )
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
            logger.warning(
                "structured_llm_execution_failed stage=%s attempt=%s code=response_schema_error parsed_payload=%s",
                stage,
                attempt_index,
                dumps_for_log(parsed_payload),
            )
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

        logger.info(
            "structured_llm_execution_completed stage=%s attempt=%s parsed=%s parsed_payload=%s",
            stage,
            attempt_index,
            parsed is not None,
            dumps_for_log(parsed_payload),
        )
        return self._result(parsed, errors, stage, attempt_index, request_payload, response_payload, raw_text)

    def _build_payload(
        self,
        prompt: str,
        response_format: Mapping[str, Any] | str | None,
        extra_params: Mapping[str, Any],
        model: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": _normalize_response_format(response_format),
        }
        payload.update({"enable_thinking": False})
        payload.update(extract_param(extra_params))
        return payload

    def _resolve_request_url(self, config: LLMConfig) -> str:
        normalized_base_url = config.base_url.rstrip("/")
        normalized_path = config.chat_completions_path or "/chat/completions"
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        return f"{normalized_base_url}{normalized_path}"

    def _build_headers(self, config: LLMConfig) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

    def _load_env(self) -> dict[str, str]:
        return _load_env_file(self.env_path)

    def _image_path_to_data_url(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.exists():
            raise LLMClientError(f"image path not found: {image_path}")
        mime_type, _ = mimetypes.guess_type(path.name)
        if not mime_type:
            mime_type = "application/octet-stream"
        binary = path.read_bytes()
        encoded = base64.b64encode(binary).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _build_multimodal_content(
        self,
        *,
        prompt: str,
        image_urls: list[str] | None,
        image_paths: list[str] | None,
    ) -> list[dict[str, Any]]:
        urls = [item for item in (image_urls or []) if item]
        paths = [item for item in (image_paths or []) if item]
        if not urls and not paths:
            raise LLMClientError("invalid_image_input: image_urls or image_paths is required for multimodal call")

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for url in urls:
            content.append({"type": "image_url", "image_url": {"url": url}})
        for path in paths:
            content.append({"type": "image_url", "image_url": {"url": self._image_path_to_data_url(path)}})
        return content

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
