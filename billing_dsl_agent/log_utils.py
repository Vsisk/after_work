from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_LOGGER_NAME = "billing_dsl_agent"
_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def get_logger(name: str) -> logging.Logger:
    _configure_package_logger()
    return logging.getLogger(name)


def dumps_for_log(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return _truncate_if_needed(text)


def _configure_package_logger() -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(_resolve_log_level())
    logger.propagate = False


def _resolve_log_level() -> int:
    level_name = str(os.getenv("BILLING_DSL_AGENT_LOG_LEVEL", "INFO")).upper()
    return getattr(logging, level_name, logging.INFO)


def _truncate_if_needed(text: str) -> str:
    max_chars_raw = os.getenv("BILLING_DSL_AGENT_LOG_MAX_CHARS", "").strip()
    if not max_chars_raw:
        return text

    try:
        max_chars = int(max_chars_raw)
    except ValueError:
        return text

    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...<truncated {len(text) - max_chars} chars>"


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump(mode="python")
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return repr(value)
