from __future__ import annotations

from dataclasses import dataclass, field

from billing_dsl_agent.ast_builder import ASTBuilder
from billing_dsl_agent.dsl_renderer import DSLRenderer
from billing_dsl_agent.environment import EnvironmentBuilder
from billing_dsl_agent.log_utils import dumps_for_log, get_logger
from billing_dsl_agent.llm_planner import LLMPlanner
from billing_dsl_agent.models import (
    GenerateDSLDebug,
    GenerateDSLRequest,
    GenerateDSLResponse,
    LLMErrorRecord,
    ValidationIssue,
    ValidationResult,
)
from billing_dsl_agent.plan_validator import PlanValidator
from billing_dsl_agent.resource_loader import ResourceLoader
from billing_dsl_agent.resource_normalizer import ResourceNormalizer

logger = get_logger(__name__)


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
        logger.info("dsl_generation_started request=%s", dumps_for_log(request))
        loaded = self.resource_loader.load(request.site_id, request.project_id)
        logger.info("resource_load_completed site_id=%s project_id=%s", request.site_id, request.project_id)
        registry = self.resource_normalizer.normalize(loaded)
        logger.info(
            "resource_normalization_completed contexts=%s bos=%s functions=%s",
            len(registry.contexts),
            len(registry.bos),
            len(registry.functions),
        )
        filtered_env = self.environment_builder.build_filtered_environment(
            node_info=request.node_def,
            user_query=request.user_requirement,
            registry=registry,
        )
        logger.info(
            "environment_filter_completed global_contexts=%s local_contexts=%s bos=%s functions=%s",
            len(filtered_env.selected_global_context_ids),
            len(filtered_env.selected_local_context_ids),
            len(filtered_env.selected_bo_ids),
            len(filtered_env.selected_function_ids),
        )
        plan = self.llm_planner.plan(request.user_requirement, request.node_def, filtered_env)
        logger.info(
            "plan_generation_completed definitions=%s return_type=%s diagnostics=%s",
            len(plan.definitions),
            getattr(plan.return_expr, "type", ""),
            len(plan.diagnostics),
        )
        plan_validation = self.plan_validator.validate(plan, filtered_env)
        debug = self._build_debug(filtered_env, plan_validation)
        logger.info(
            "plan_validation_completed is_valid=%s issue_codes=%s repair_attempts=%s",
            plan_validation.is_valid,
            [item.code for item in plan_validation.issues],
            len(plan_validation.repair_attempts),
        )
        if not plan_validation.is_valid:
            logger.warning("dsl_generation_failed reason=plan_validation_failed issues=%s", dumps_for_log(plan_validation.issues))
            return GenerateDSLResponse(
                success=False,
                plan=plan_validation.repaired_plan,
                validation=plan_validation,
                failure_reason="plan validation failed",
                debug=debug,
            )

        valid_plan = plan_validation.repaired_plan or plan
        ast = self.ast_builder.build_program_from_plan(valid_plan, filtered_env)
        logger.info("ast_build_completed root_node=%s", type(ast).__name__)
        dsl = self.dsl_renderer.render(ast)
        logger.info("dsl_render_completed dsl=%s", dsl)
        final_validation = self.final_validator.validate(dsl)
        final_validation.repair_attempts = list(plan_validation.repair_attempts)
        final_validation.llm_errors = list(plan_validation.llm_errors)
        logger.info(
            "final_validation_completed is_valid=%s issue_codes=%s",
            final_validation.is_valid,
            [item.code for item in final_validation.issues],
        )
        return GenerateDSLResponse(
            success=final_validation.is_valid,
            dsl=dsl,
            plan=valid_plan,
            ast=ast,
            validation=final_validation,
            failure_reason="" if final_validation.is_valid else "final validation failed",
            debug=debug,
        )

    def _build_debug(self, filtered_env, plan_validation: ValidationResult) -> GenerateDSLDebug:
        selection_debug = filtered_env.selection_debug
        selection_errors: list[LLMErrorRecord] = []
        if selection_debug is not None:
            selection_errors.extend(selection_debug.global_context.llm_errors)
            selection_errors.extend(selection_debug.local_context.llm_errors)
            selection_errors.extend(selection_debug.bo.llm_errors)
            selection_errors.extend(selection_debug.function.llm_errors)
        all_errors = self._dedupe_llm_errors(
            [*selection_errors, *self.llm_planner.llm_errors, *plan_validation.llm_errors]
        )
        return GenerateDSLDebug(
            resource_selection=selection_debug,
            plan_attempts=list(self.llm_planner.plan_attempts),
            repair_attempts=list(plan_validation.repair_attempts),
            llm_errors=all_errors,
        )

    def _dedupe_llm_errors(self, errors: list[LLMErrorRecord]) -> list[LLMErrorRecord]:
        seen: set[tuple[str, str, str, str]] = set()
        deduped: list[LLMErrorRecord] = []
        for item in errors:
            key = (item.stage, item.code, item.message, item.exception_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
