"""Resource matcher protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.plan import ResolvedEnvironment, ResourceBinding


class ResourceMatcher(Protocol):
    """Match intent with available environment resources."""

    def match(self, intent: NodeIntent, env: ResolvedEnvironment) -> ResourceBinding:
        ...
