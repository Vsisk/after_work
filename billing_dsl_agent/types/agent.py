"""Agent-facing planning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class PlanDraft:
    """Structured plan proposed by the LLM planning stage."""

    intent_summary: str
    semantic_slots: Dict[str, Any] = field(default_factory=dict)
    context_refs: List[str] = field(default_factory=list)
    bo_refs: List[Dict[str, Any]] = field(default_factory=list)
    function_refs: List[str] = field(default_factory=list)
    expression_pattern: str = ""
    raw_plan: Dict[str, Any] = field(default_factory=dict)
