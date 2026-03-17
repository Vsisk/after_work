"""Agent entry service that can use an LLM parser or local fallback chain."""

from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.services.llm_requirement_parser import LLMRequirementParser
from billing_dsl_agent.services.orchestrator import CodeAgentOrchestrator
from billing_dsl_agent.types.request_response import GenerateDSLRequest, GenerateDSLResponse


@dataclass(slots=True)
class GenerateDSLAgentService:
    """Top-level DSL generation service with optional LLM parser entrypoint."""

    orchestrator: CodeAgentOrchestrator
    llm_parser: LLMRequirementParser | None = None
    enable_llm_parser: bool = True

    def generate(self, request: GenerateDSLRequest) -> GenerateDSLResponse:
        if not self.enable_llm_parser or self.llm_parser is None:
            return self.orchestrator.generate(request)

        intent = self.llm_parser.parse_request(request)
        env = self.orchestrator.environment_resolver.resolve(
            global_context_vars=request.global_context_vars,
            local_context_vars=request.local_context_vars,
            available_bos=request.available_bos,
            available_functions=request.available_functions,
        )
        binding = self.orchestrator.resource_matcher.match(intent, env)

        if not binding.is_satisfied:
            return GenerateDSLResponse(
                success=False,
                intent=intent,
                resolved_environment=env,
                resource_binding=binding,
                failure_reason="Unsatisfied resources for intent.",
            )

        plan = self.orchestrator.value_planner.build_plan(intent, binding, env)
        generated_dsl = self.orchestrator.dsl_renderer.render(plan)
        validation_result = self.orchestrator.validator.validate(generated_dsl, request, env)
        explanation = self.orchestrator.explanation_builder.build(intent, binding, plan)

        return GenerateDSLResponse(
            success=validation_result.is_valid,
            dsl_code=generated_dsl.to_text(),
            generated_dsl=generated_dsl,
            intent=intent,
            resolved_environment=env,
            resource_binding=binding,
            value_plan=plan,
            explanation=explanation,
            validation_result=validation_result,
            failure_reason=None if validation_result.is_valid else "Validation failed.",
        )
