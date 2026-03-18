"""Agent entry service for the orchestrated DSL generation flow."""

from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.services.orchestrator import CodeAgentOrchestrator
from billing_dsl_agent.types.request_response import GenerateDSLRequest, GenerateDSLResponse


@dataclass(slots=True)
class GenerateDSLAgentService:
    """Top-level DSL generation service."""

    orchestrator: CodeAgentOrchestrator

    def generate(self, request: GenerateDSLRequest) -> GenerateDSLResponse:
        return self.orchestrator.generate(request)
