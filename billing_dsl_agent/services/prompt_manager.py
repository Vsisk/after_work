from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")
_DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompt.json"


class PromptManagerError(ValueError):
    """Raised when prompt definitions are missing or invalid."""


@dataclass(slots=True)
class PromptManager:
    prompt_path: Path = _DEFAULT_PROMPT_PATH

    def load_prompts(self) -> dict[str, dict[str, str]]:
        try:
            raw = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PromptManagerError(f"prompt file not found: {self.prompt_path}") from exc
        except json.JSONDecodeError as exc:
            raise PromptManagerError(f"prompt file is not valid JSON: {self.prompt_path}") from exc

        if not isinstance(raw, dict):
            raise PromptManagerError("prompt file root must be a JSON object")

        prompts: dict[str, dict[str, str]] = {}
        for prompt_key, value in raw.items():
            if not isinstance(prompt_key, str) or not isinstance(value, dict):
                raise PromptManagerError("each prompt must use the format {'promptKey': {'zh': '', 'en': ''}}")

            localized: dict[str, str] = {}
            for lang, template in value.items():
                if not isinstance(lang, str) or not isinstance(template, str):
                    raise PromptManagerError("prompt language values must be strings")
                localized[lang] = template
            prompts[prompt_key] = localized
        return prompts

    def get_prompt(self, prompt_key: str, lang: str) -> str:
        prompts = self.load_prompts()
        template_group = prompts.get(prompt_key)
        if template_group is None:
            raise PromptManagerError(f"prompt key not found: {prompt_key}")

        template = template_group.get(lang)
        if template is not None:
            return template

        fallback = template_group.get("zh") or template_group.get("en")
        if fallback is not None:
            return fallback
        raise PromptManagerError(f"prompt language not found for key={prompt_key!r}, lang={lang!r}")

    def render_prompt(
        self,
        prompt_key: str,
        lang: str,
        params: Mapping[str, Any] | None = None,
    ) -> str:
        template = self.get_prompt(prompt_key=prompt_key, lang=lang)
        resolved_params = dict(params or {})
        required_keys = sorted(set(_PLACEHOLDER_PATTERN.findall(template)))
        missing = [key for key in required_keys if key not in resolved_params]
        if missing:
            raise PromptManagerError(
                f"missing prompt params for key={prompt_key!r}: {', '.join(missing)}"
            )

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(resolved_params[key])

        return _PLACEHOLDER_PATTERN.sub(replace, template)

