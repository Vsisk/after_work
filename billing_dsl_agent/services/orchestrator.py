"""Pipeline orchestrator for the LLM-first DSL code agent."""

from __future__ import annotations

from dataclasses import dataclass

from billing_dsl_agent.protocols.explainer import ExplanationBuilder
from billing_dsl_agent.protocols.planner import ValuePlanner
from billing_dsl_agent.protocols.renderer import DSLRenderer
from billing_dsl_agent.protocols.resolver import EnvironmentResolver
from billing_dsl_agent.protocols.validator import Validator
from billing_dsl_agent.services.llm_planner import LLMPlanner
from billing_dsl_agent.services.plan_validator import PlanValidator
from billing_dsl_agent.types.request_response import GenerateDSLRequest, GenerateDSLResponse


@dataclass(slots=True)
class CodeAgentOrchestrator:
    """Coordinates LLM planning, local validation, rendering and final validation."""

    llm_planner: LLMPlanner
    environment_resolver: EnvironmentResolver
    plan_validator: PlanValidator
    value_planner: ValuePlanner
    dsl_renderer: DSLRenderer
    validator: Validator
    explanation_builder: ExplanationBuilder

    def generate(self, request: GenerateDSLRequest) -> GenerateDSLResponse:
        env = self.environment_resolver.resolve(
            global_context_vars=request.global_context_vars,
            local_context_vars=request.local_context_vars,
            available_bos=request.available_bos,
            available_functions=request.available_functions,
        )
        plan_draft = self.llm_planner.plan(request.user_requirement, request.node_def, env)
        if not plan_draft.raw_plan.get("target_node_path"):
            plan_draft.raw_plan["target_node_path"] = request.node_def.node_path
        intent = self.llm_planner.draft_to_intent(plan_draft, request.node_def, request.user_requirement)
        plan_validation = self.plan_validator.validate(plan_draft, env)
        if not plan_validation.is_valid:
            return GenerateDSLResponse(
                success=False,
                plan_draft=plan_draft,
                intent=intent,
                resolved_environment=env,
                validation_result=plan_validation,
                failure_reason="Plan validation failed.",
            )

        plan = self.value_planner.build_plan(plan_draft, env)
        generated_dsl = self.dsl_renderer.render(plan)
        validation_result = self.validator.validate(generated_dsl, request, env)
        explanation = self.explanation_builder.build(plan_draft, plan)

        return GenerateDSLResponse(
            success=validation_result.is_valid,
            dsl_code=generated_dsl.to_text(),
            plan_draft=plan_draft,
            generated_dsl=generated_dsl,
            intent=intent,
            resolved_environment=env,
            value_plan=plan,
            explanation=explanation,
            validation_result=validation_result,
            failure_reason=None if validation_result.is_valid else "Validation failed.",
        )
