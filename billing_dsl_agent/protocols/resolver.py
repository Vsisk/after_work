"""Environment resolver protocol."""

from __future__ import annotations

from typing import List, Protocol

from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.context import ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.plan import ResolvedEnvironment


class EnvironmentResolver(Protocol):
    """Resolve raw resources into unified environment."""

    def resolve(
        self,
        global_context_vars: List[ContextVarDef],
        local_context_vars: List[ContextVarDef],
        available_bos: List[BODef],
        available_functions: List[FunctionDef],
    ) -> ResolvedEnvironment:
        ...
