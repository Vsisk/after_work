from __future__ import annotations

from dataclasses import dataclass, field

from billing_dsl_agent.ast_builder import ASTBuilder
from billing_dsl_agent.datatype_classifier import DatatypeClassifier
from billing_dsl_agent.datatype_resolver import DatatypeResolver
from billing_dsl_agent.datatype_validator import DatatypeValidator
from billing_dsl_agent.dsl_renderer import DSLRenderer
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.expression_ref_validator import ExpressionRefValidator
from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import GenerateDSLRequest, GenerateDSLResponse, ValidationIssue, ValidationResult
from billing_dsl_agent.plan_validator import PlanValidator
from billing_dsl_agent.resource_loader import ResourceLoader
from billing_dsl_agent.resource_normalizer import ResourceNormalizer
from billing_dsl_agent.runtime_config_loader import RuntimeConfig, RuntimeConfigLoader


@dataclass(slots=True)
class FinalValidator:
    def validate(self, dsl: str) -> ValidationResult:
        issues: list[ValidationIssue] = []
        if not dsl.strip():
            issues.append(ValidationIssue(code="dsl_empty", message="dsl is empty", path="dsl"))
        if dsl.count("(") != dsl.count(")"):
            issues.append(
                ValidationIssue(
                    code="dsl_parentheses_unbalanced",
                    message="parentheses not balanced",
                    path="dsl",
                )
            )
        return ValidationResult(is_valid=not issues, issues=issues)


@dataclass(slots=True)
class DSLAgent:
    llm_planner: LLMPlanner
    resource_loader: ResourceLoader
    global_config: dict | None = None
    resource_normalizer: ResourceNormalizer = field(default_factory=ResourceNormalizer)
    environment_builder: EnvironmentBuilder = field(default_factory=EnvironmentBuilder)
    plan_validator: PlanValidator | None = None
    runtime_config_loader: RuntimeConfigLoader = field(default_factory=RuntimeConfigLoader)
    datatype_classifier: DatatypeClassifier = field(default_factory=DatatypeClassifier)
    datatype_resolver: DatatypeResolver = field(default_factory=DatatypeResolver)
    expression_ref_validator: ExpressionRefValidator = field(default_factory=ExpressionRefValidator)
    datatype_validator: DatatypeValidator | None = None
    ast_builder: ASTBuilder = field(default_factory=ASTBuilder)
    dsl_renderer: DSLRenderer = field(default_factory=DSLRenderer)
    final_validator: FinalValidator = field(default_factory=FinalValidator)
    runtime_config: RuntimeConfig = field(init=False)

    def __post_init__(self) -> None:
        if self.plan_validator is None:
            self.plan_validator = PlanValidator(planner=self.llm_planner)
        # Fail-fast runtime config load/validate happens in agent initialization.
        self.runtime_config = self.runtime_config_loader.load(self.global_config)
        if self.datatype_validator is None:
            self.datatype_validator = DatatypeValidator(expression_validator=self.expression_ref_validator)

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
        ast = self.ast_builder.build_program_from_plan(valid_plan, filtered_env)
        dsl = self.dsl_renderer.render(ast)
        final_validation = self.final_validator.validate(dsl)
        datatype_kind = self.datatype_classifier.classify(
            user_query=request.user_requirement,
            node_info=request.node_def,
            value_plan=valid_plan,
            candidate_resources=filtered_env,
            datatype_defaults=self.runtime_config.datatype_defaults,
        )
        datatype_obj = self.datatype_resolver.resolve(
            datatype_kind=datatype_kind,
            runtime_config=self.runtime_config,
            user_query=request.user_requirement,
            node_info=request.node_def,
            candidate_resources=filtered_env,
        )
        datatype_validation = self.datatype_validator.validate(datatype_obj=datatype_obj, env=filtered_env)
        success = final_validation.is_valid and datatype_validation.is_valid
        return GenerateDSLResponse(
            success=success,
            dsl=dsl,
            plan=valid_plan,
            ast=ast,
            validation=final_validation,
            datatype=datatype_obj,
            datatype_plan={"kind": datatype_kind.value},
            datatype_validation=datatype_validation.model_dump(),
            failure_reason="" if success else "final validation failed",
        )
