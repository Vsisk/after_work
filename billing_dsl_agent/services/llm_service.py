from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from billing_dsl_agent.services.llm_client import OpenAILLMClient


@dataclass(slots=True)
class PromptDrivenLLMService:
    client: OpenAILLMClient = field(default_factory=OpenAILLMClient)

    def generate(
        self,
        prompt_key: str,
        lang: str,
        prompt_params: Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.client.invoke(
            prompt_key=prompt_key,
            lang=lang,
            prompt_params=prompt_params,
            response_format=response_format,
            **kwargs,
        )

