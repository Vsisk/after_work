"""Default environment resolver service."""

from __future__ import annotations

from typing import List

from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.context import ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.plan import ResolvedEnvironment


class DefaultEnvironmentResolver:
    """Minimal environment resolver that returns provided resources as-is."""

    def resolve(
        self,
        global_context_vars: List[ContextVarDef],
        local_context_vars: List[ContextVarDef],
        available_bos: List[BODef],
        available_functions: List[FunctionDef],
    ) -> ResolvedEnvironment:
        # TODO: add variable duplicate checks across global/local scopes.
        # TODO: add local context inheritance expansion from parent node chain.
        return ResolvedEnvironment(
            global_context_vars=list(global_context_vars),
            local_context_vars=list(local_context_vars),
            available_bos=list(available_bos),
            available_functions=list(available_functions),
        )
