from __future__ import annotations

from dataclasses import dataclass, field

from billing_dsl_agent.ast_builder import ASTBuilder
from billing_dsl_agent.dsl_renderer import DSLRenderer
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import GenerateDSLRequest, GenerateDSLResponse, ValidationResult
from billing_dsl_agent.plan_validator import PlanValidator
from billing_dsl_agent.resource_loader import ResourceLoader
from billing_dsl_agent.resource_normalizer import ResourceNormalizer


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
class DSLAgent:
    llm_planner: LLMPlanner
    resource_loader: ResourceLoader
    resource_normalizer: ResourceNormalizer = field(default_factory=ResourceNormalizer)
    environment_builder: EnvironmentBuilder = field(default_factory=EnvironmentBuilder)
    plan_validator: PlanValidator | None = None
    ast_builder: ASTBuilder = field(default_factory=ASTBuilder)
    dsl_renderer: DSLRenderer = field(default_factory=DSLRenderer)
    final_validator: FinalValidator = field(default_factory=FinalValidator)

    def __post_init__(self) -> None:
        if self.plan_validator is None:
            self.plan_validator = PlanValidator(planner=self.llm_planner)

    def generate_dsl(self, request: GenerateDSLRequest) -> GenerateDSLResponse:
        loaded = self.resource_loader.load(request.site_id, request.project_id)
        registry = self.resource_normalizer.normalize(loaded)
        filtered_env = self.environment_builder.build_filtered_environment(
            node_info=request.node_def,
            user_query=request.user_requirement,
            registry=registry,
        )
        plan = self.llm_planner.plan(request.user_requirement, request.node_def, filtered_env)
        plan_validation = self.plan_validator.validate(plan, filtered_env)
        if not plan_validation.is_valid:
            return GenerateDSLResponse(
                success=False,
                plan=plan_validation.repaired_plan,
                validation=plan_validation,
                failure_reason="plan validation failed",
            )

        valid_plan = plan_validation.repaired_plan or plan
        ast = self.ast_builder.build_ast(valid_plan, filtered_env)
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
