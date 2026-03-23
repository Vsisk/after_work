from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from billing_dsl_agent.ast_builder import ASTBuilder
from billing_dsl_agent.dsl_renderer import EDSLRenderer
from billing_dsl_agent.environment import EnvironmentBuilder, NodeContextResolver
from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import (
    GenerateDSLRequest,
    GenerateDSLResponse,
    GenerateExpressionRequest,
    GenerateExpressionResponse,
    ValidationResult,
)
from billing_dsl_agent.plan_validator import PlanValidator
from billing_dsl_agent.resource_manager import ResourceManager
from billing_dsl_agent.schema_provider import SchemaProvider


@dataclass(slots=True)
class FinalValidator:
    def validate(self, dsl: str) -> ValidationResult:
        issues: list[str] = []
        if not dsl.strip():
            issues.append("dsl is empty")
        if dsl.count("(") != dsl.count(")"):
            issues.append("parentheses not balanced")
        return ValidationResult(is_valid=not issues, issues=issues)


@dataclass(slots=True)
class ExpressionAgent:
    schema_provider: SchemaProvider = field(default_factory=SchemaProvider)
    context_resolver: NodeContextResolver = field(default_factory=NodeContextResolver)
    resource_manager: ResourceManager = field(default_factory=ResourceManager)
    llm_planner: LLMPlanner | None = None
    plan_validator: PlanValidator | None = None
    ast_builder: ASTBuilder = field(default_factory=ASTBuilder)
    renderer: EDSLRenderer = field(default_factory=EDSLRenderer)

    def __post_init__(self) -> None:
        if self.llm_planner is None:
            raise ValueError("llm_planner is required")
        if self.plan_validator is None:
            self.plan_validator = PlanValidator(planner=self.llm_planner)

    def generate_expression(self, request: GenerateExpressionRequest) -> GenerateExpressionResponse:
        loaded = self.schema_provider.load_all(site_id=request.site_id, project_id=request.project_id)
        environment = self.context_resolver.resolve(node_info=request.node_info, loaded_schemas=loaded)
        candidate_set = self.resource_manager.select_candidates_for_environment(
            user_query=request.user_query,
            node_info=request.node_info,
            environment=environment,
        )
        planning_environment = self.resource_manager.narrow_environment(environment, candidate_set)
        plan = self.llm_planner.plan(request.user_query, request.node_info, candidate_set)

        assert self.plan_validator is not None
        validation = self.plan_validator.validate(plan, planning_environment)
        if not validation.is_valid:
            return GenerateExpressionResponse(
                success=False,
                failure_reason="plan validation failed",
                plan=validation.repaired_plan if request.debug else None,
                validation=validation if request.debug else None,
            )

        valid_plan = validation.repaired_plan or plan
        ast = self.ast_builder.build(valid_plan)
        expression = self.renderer.render(ast)
        response = GenerateExpressionResponse(success=True, edsl_expression=expression)
        if request.debug:
            response.plan = valid_plan
            response.validation = validation
        return response


@dataclass(slots=True)
class DSLAgent:
    llm_planner: LLMPlanner
    environment_builder: EnvironmentBuilder = field(default_factory=EnvironmentBuilder)
    plan_validator: PlanValidator | None = None
    ast_builder: ASTBuilder = field(default_factory=ASTBuilder)
    dsl_renderer: EDSLRenderer = field(default_factory=EDSLRenderer)
    final_validator: FinalValidator = field(default_factory=FinalValidator)

    def __post_init__(self) -> None:
        if self.plan_validator is None:
            self.plan_validator = PlanValidator(planner=self.llm_planner)

    def generate_dsl(self, request: GenerateDSLRequest) -> GenerateDSLResponse:
        env = self.environment_builder.build_environment(request)
        plan = self.llm_planner.plan(request.user_requirement, request.node_def, env)
        assert self.plan_validator is not None
        plan_validation = self.plan_validator.validate(plan, env)
        if not plan_validation.is_valid:
            return GenerateDSLResponse(
                success=False,
                plan=plan_validation.repaired_plan,
                validation=plan_validation,
                failure_reason="plan validation failed",
            )

        valid_plan = plan_validation.repaired_plan or plan
        ast = self.ast_builder.build(valid_plan)
        dsl = self.dsl_renderer.render(ast)
        final_validation = self.final_validator.validate(dsl)
        return GenerateDSLResponse(
            success=final_validation.is_valid,
            dsl=dsl,
            plan=valid_plan,
            ast=ast,
            validation=final_validation,
            failure_reason="" if final_validation.is_valid else "final validation failed",
        )


def generate_expression(request: GenerateExpressionRequest, planner: LLMPlanner, provider: SchemaProvider | None = None) -> GenerateExpressionResponse:
    return ExpressionAgent(llm_planner=planner, schema_provider=provider or SchemaProvider()).generate_expression(request)


def generate_dsl(request: GenerateDSLRequest, planner: LLMPlanner) -> GenerateDSLResponse:
    return DSLAgent(llm_planner=planner).generate_dsl(request)
