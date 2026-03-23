"""Compatibility wrapper around the new LLM planning stage."""

from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.services.llm_planner import LLMPlanner
from billing_dsl_agent.types.intent import NodeIntent
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import ResolvedEnvironment
from billing_dsl_agent.types.request_response import GenerateDSLRequest


@dataclass(slots=True)
class LLMRequirementParser:
    """Legacy compatibility wrapper that derives NodeIntent from PlanDraft."""

    planner: LLMPlanner

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        draft = self.planner.plan(user_requirement, node_def, ResolvedEnvironment())
        return self.planner.draft_to_intent(draft, node_def, user_requirement)

    def parse_request(self, request: GenerateDSLRequest) -> NodeIntent:
        env = ResolvedEnvironment(
            global_context_vars=list(request.global_context_vars or []),
            local_context_vars=list(request.local_context_vars or []),
            available_bos=list(request.available_bos or []),
            available_functions=list(request.available_functions or []),
        )
        draft = self.planner.plan(request.user_requirement, request.node_def, env)
        return self.planner.draft_to_intent(draft, request.node_def, request.user_requirement)
