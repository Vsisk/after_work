"""Pipeline orchestrator for DSL code agent."""

from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.protocols.explainer import ExplanationBuilder
from billing_dsl_agent.protocols.matcher import ResourceMatcher
from billing_dsl_agent.protocols.parser import RequirementParser
from billing_dsl_agent.protocols.planner import ValuePlanner
from billing_dsl_agent.protocols.renderer import DSLRenderer
from billing_dsl_agent.protocols.resolver import EnvironmentResolver
from billing_dsl_agent.protocols.validator import Validator
from billing_dsl_agent.types.request_response import GenerateDSLRequest, GenerateDSLResponse


@dataclass(slots=True)
class CodeAgentOrchestrator:
    """Coordinates parsing, resource matching, planning, rendering and validation."""

    parser: RequirementParser
    environment_resolver: EnvironmentResolver
    resource_matcher: ResourceMatcher
    value_planner: ValuePlanner
    dsl_renderer: DSLRenderer
    validator: Validator
    explanation_builder: ExplanationBuilder

    def generate(self, request: GenerateDSLRequest) -> GenerateDSLResponse:
        intent = self.parser.parse(request.user_requirement, request.node_def)
        env = self.environment_resolver.resolve(
            global_context_vars=request.global_context_vars,
            local_context_vars=request.local_context_vars,
            available_bos=request.available_bos,
            available_functions=request.available_functions,
        )
        binding = self.resource_matcher.match(intent, env)

        if not binding.is_satisfied:
            return GenerateDSLResponse(
                success=False,
                intent=intent,
                resolved_environment=env,
                resource_binding=binding,
                failure_reason="Unsatisfied resources for intent.",
            )

        plan = self.value_planner.build_plan(intent, binding, env)
        generated_dsl = self.dsl_renderer.render(plan)
        validation_result = self.validator.validate(generated_dsl, request, env)
        explanation = self.explanation_builder.build(intent, binding, plan)

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
