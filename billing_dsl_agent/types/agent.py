"""Agent-facing planning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class PlanDraft:
    """Structured planning draft returned by an LLM-facing parser stage."""

    intent_summary: str
    semantic_slots: Dict[str, Any] = field(default_factory=dict)
    candidate_resources: Dict[str, List[str]] = field(default_factory=dict)
    expression_pattern: str = ""
    source_types: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)
