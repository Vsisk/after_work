from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Mapping, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from billing_dsl_agent.models import LLMErrorRecord, LLMAttemptRecord
from billing_dsl_agent.services.llm_post_processor import extract_response_text
from billing_dsl_agent.services.prompt_manager import PromptManager, PromptManagerError

ModelT = TypeVar("ModelT")


class PromptStructuredClient(Protocol):
    def generate_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        ...


class InvokeRawStructuredClient(Protocol):
    def invoke_raw(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        ...


class LegacyStructuredClient(Protocol):
    def create_plan(self, payload: dict[str, Any]) -> Any:
        ...


@dataclass(slots=True)
class StructuredExecutionResult(Generic[ModelT]):
    parsed: ModelT | None
    errors: list[LLMErrorRecord]
    attempt: LLMAttemptRecord
    raw_text: str = ""
    raw_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class StructuredLLMExecutor:
    client: Any
    prompt_manager: PromptManager = field(default_factory=PromptManager)
    default_lang: str = "zh"

    def execute(
        self,
        *,
        prompt_key: str,
        prompt_params: Mapping[str, Any] | None,
        response_model: type[BaseModel] | None,
        stage: str,
        attempt_index: int = 1,
        lang: str | None = None,
        response_parser: Callable[[dict[str, Any]], ModelT] | None = None,
        **kwargs: Any,
    ) -> StructuredExecutionResult[ModelT]:
        active_lang = lang or self.default_lang
        request_payload: dict[str, Any] | None = None
        response_payload: dict[str, Any] | None = None
        raw_text = ""
        errors: list[LLMErrorRecord] = []

        response_format = self._build_response_format(response_model)

        try:
            if hasattr(self.client, "generate_raw"):
                raw_invocation = self.client.generate_raw(
                    prompt_key=prompt_key,
                    lang=active_lang,
                    prompt_params=prompt_params,
                    response_format=response_format,
                    **kwargs,
                )
                request_payload = self._as_dict(getattr(raw_invocation, "request_payload", None))
                response_payload = self._as_dict(getattr(raw_invocation, "response_payload", None))
            elif hasattr(self.client, "invoke_raw"):
                raw_invocation = self.client.invoke_raw(
                    prompt_key=prompt_key,
                    lang=active_lang,
                    prompt_params=prompt_params,
                    response_format=response_format,
                    **kwargs,
                )
                request_payload = self._as_dict(getattr(raw_invocation, "request_payload", None))
                response_payload = self._as_dict(getattr(raw_invocation, "response_payload", None))
            elif hasattr(self.client, "create_plan"):
                prompt = self.prompt_manager.render_prompt(
                    prompt_key=prompt_key,
                    lang=active_lang,
                    params=prompt_params,
                )
                request_payload = {
                    "mode": stage,
                    "prompt_key": prompt_key,
                    "prompt": prompt,
                    "input": dict(prompt_params or {}),
                    "response_format": response_format,
                }
                request_payload.update(dict(prompt_params or {}))
                raw_response = self.client.create_plan(request_payload)
                response_payload = self._normalize_legacy_response(raw_response)
            else:
                raise TypeError("structured llm client must implement generate_raw()/invoke_raw() or create_plan()")
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

    def _normalize_legacy_response(self, raw_response: Any) -> dict[str, Any] | None:
        if raw_response is None:
            return None
        if isinstance(raw_response, dict):
            return dict(raw_response)
        if isinstance(raw_response, str):
            return {"output_text": raw_response}
        return {"content": {"result": raw_response}}

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
