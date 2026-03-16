"""Default resource matcher service."""

from __future__ import annotations

from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.plan import ResolvedEnvironment, ResourceBinding


class DefaultResourceMatcher:
    """Minimal matcher that returns empty satisfied binding."""

    def match(self, intent: NodeIntent, env: ResolvedEnvironment) -> ResourceBinding:
        # TODO: parse intent operations/constraints to map context vars and fields.
        # TODO: resolve BO bindings with query mode inference (select/select_one/fetch/fetch_one).
        # TODO: resolve function bindings and import requirements.
        return ResourceBinding()
