"""Requirement parser protocol."""

from __future__ import annotations

from typing import Protocol

from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.node import NodeDef


class RequirementParser(Protocol):
    """Parse user requirement into structured node intent."""

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        ...
