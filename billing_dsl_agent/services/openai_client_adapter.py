"""Mockable OpenAI client adapter for future structured planning integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from billing_dsl_agent.types.agent import PlanDraft


class OpenAIClientAdapter(Protocol):
    """Protocol for future structured-output planning calls."""

    def create_plan_draft(self, payload: Dict[str, Any]) -> Optional[PlanDraft]:
        """Return one structured plan draft compatible with PlanDraft."""


@dataclass(slots=True)
class StubOpenAIClientAdapter:
    """Non-networking adapter used as default until real API wiring is enabled."""

    draft: Optional[PlanDraft] = None
    recorded_payloads: List[Dict[str, Any]] = field(default_factory=list)

    def create_plan_draft(self, payload: Dict[str, Any]) -> Optional[PlanDraft]:
        self.recorded_payloads.append(payload)
        return self.draft
