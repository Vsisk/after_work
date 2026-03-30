from __future__ import annotations

import json
from typing import Any, Mapping


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, Mapping):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
                continue
            inner_text = item.get("content")
            if isinstance(inner_text, str):
                parts.append(inner_text)
        return "".join(parts).strip()

    return ""


def extract_response_text(response_payload: Mapping[str, Any]) -> str:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, Mapping):
            message = first_choice.get("message")
            if isinstance(message, Mapping):
                content = _extract_text_from_content(message.get("content"))
                if content:
                    return content

    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = response_payload.get("output")
    if isinstance(output, list):
        fragments: list[str] = []
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if not isinstance(content_item, Mapping):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    fragments.append(text)
        combined = "".join(fragments).strip()
        if combined:
            return combined

    return ""


def _normalize_to_dict(parsed: Any) -> dict[str, Any]:
    if isinstance(parsed, dict):
        return dict(parsed)
    return {"result": parsed}


def post_process_response(response_payload: Mapping[str, Any]) -> dict[str, Any]:
    text = extract_response_text(response_payload)
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"result": text}

    return _normalize_to_dict(parsed)
