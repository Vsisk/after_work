from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from billing_dsl_agent.log_utils import dumps_for_log, get_logger
from billing_dsl_agent.models import (
    BinaryOpPlanNode,
    ContextRefPlanNode,
    ExprPlanNode,
    FilteredEnvironment,
    FunctionCallPlanNode,
    IfPlanNode,
    IndexAccessPlanNode,
    ListLiteralPlanNode,
    LocalRefPlanNode,
    ProgramPlan,
    ProgramPlanLimits,
    QueryCallPlanNode,
    UnaryOpPlanNode,
    ValidationIssue,
    ValidationResult,
    VarRefPlanNode,
    VariableDefinitionNode,
    FieldAccessPlanNode,
    LiteralPlanNode,
)
from billing_dsl_agent.resource_manager import normalize_function_type

logger = get_logger(__name__)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED_WORDS = {"def", "return", "if", "else", "and", "or", "not"}


@dataclass(slots=True)
class NamingSQLParamTypeMatchResult:
    matched: bool
    mismatch_stage: str = ""
    reason: str = ""


class PlanRepairer(Protocol):
    def repair(
        self,
        invalid_plan: ProgramPlan,
        env: FilteredEnvironment,
        issues: list[ValidationIssue],
    ) -> ProgramPlan | None:
        ...


class PlanValidator:
    def __init__(
        self,
        planner: PlanRepairer | None = None,
        max_retries: int = 2,
        limits: ProgramPlanLimits | None = None,
    ):
        self.planner = planner
        self.max_retries = max_retries
        self.limits = limits or ProgramPlanLimits()

    def validate(self, plan: ProgramPlan, env: FilteredEnvironment) -> ValidationResult:
        current = plan
        attempts = 0
        repair_attempts = []
        llm_errors = []
        logger.info(
            "plan_validation_started definition_count=%s return_type=%s",
            len(current.definitions),
            getattr(current.return_expr, "type", ""),
        )
        while True:
            issues = self._collect_issues(current, env)
            blocking_issues = [item for item in issues if item.severity != "warning"]
            logger.info(
                "plan_validation_iteration attempt=%s blocking_issue_codes=%s warning_issue_codes=%s",
                attempts,
                [item.code for item in blocking_issues],
                [item.code for item in issues if item.severity == "warning"],
            )
            if not blocking_issues:
                logger.info("plan_validation_succeeded repair_attempts=%s", len(repair_attempts))
                return ValidationResult(
                    is_valid=True,
                    issues=issues,
                    repaired_plan=current,
                    repair_attempts=list(repair_attempts),
                    llm_errors=list(llm_errors),
                )
            if self.planner is None or attempts >= self.max_retries:
                logger.warning("plan_validation_failed attempts=%s issues=%s", attempts, dumps_for_log(blocking_issues))
                return ValidationResult(
                    is_valid=False,
                    issues=blocking_issues,
                    repaired_plan=current,
                    repair_attempts=list(repair_attempts),
                    llm_errors=list(llm_errors),
                )
            logger.info("plan_repair_started attempt=%s issues=%s", attempts + 1, dumps_for_log(blocking_issues))
            repaired = self.planner.repair(current, env, blocking_issues)
            repair_attempts = list(getattr(self.planner, "repair_attempts", repair_attempts))
            llm_errors = list(getattr(self.planner, "llm_errors", llm_errors))
            if repaired is None:
                logger.warning("plan_repair_failed attempt=%s reason=no_repaired_plan", attempts + 1)
                return ValidationResult(
                    is_valid=False,
                    issues=blocking_issues,
                    repaired_plan=current,
                    repair_attempts=list(repair_attempts),
                    llm_errors=list(llm_errors),
                )
            if _plans_equivalent(current, repaired):
                logger.warning("plan_repair_failed attempt=%s reason=no_progress", attempts + 1)
                issues = _dedupe_issues(
                    [
                        *blocking_issues,
                        issue(
                            "repair_no_progress",
                            "repair returned an equivalent invalid plan; stop repair loop",
                            "program",
                        ),
                    ]
                )
                return ValidationResult(
                    is_valid=False,
                    issues=issues,
                    repaired_plan=current,
                    repair_attempts=list(repair_attempts),
                    llm_errors=list(llm_errors),
                )
            logger.info("plan_repair_completed attempt=%s repaired_plan=%s", attempts + 1, dumps_for_log(repaired))
            current = repaired
            attempts += 1

    def _collect_issues(self, plan: ProgramPlan, env: FilteredEnvironment) -> list[ValidationIssue]:
        issues = validate_program_plan_structure(plan, self.limits)
        issues.extend(validate_program_plan_semantics(plan, env))
        return issues


def issue(code: str, message: str, path: str, severity: str = "error") -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path, severity=severity)


def validate_program_plan_structure(
    plan: ProgramPlan,
    config: ProgramPlanLimits,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    definitions = plan.definitions or []

    for diagnostic in plan.diagnostics:
        if diagnostic.severity == "error":
            issues.append(issue(diagnostic.code, diagnostic.message, diagnostic.path or "program", diagnostic.severity))

    if len(definitions) > config.max_definitions:
        issues.append(
            issue(
                "too_many_definitions",
                f"definitions exceeds limit {config.max_definitions}",
                "definitions",
            )
        )

    seen_names: set[str] = set()
    all_names = [definition.name for definition in definitions if hasattr(definition, "name")]
    defined_names: set[str] = set()

    for index, definition in enumerate(definitions):
        def_path = f"definitions[{index}]"
        name = definition.name
        name_path = f"{def_path}.name"
        if not IDENTIFIER_RE.match(name):
            issues.append(issue("invalid_definition_name", f"invalid definition name: {name}", name_path))
        if name in RESERVED_WORDS:
            issues.append(issue("reserved_definition_name", f"reserved definition name: {name}", name_path))
        if name in seen_names:
            issues.append(issue("duplicate_definition_name", f"duplicate definition name: {name}", name_path))
        seen_names.add(name)

        depth = compute_expr_depth(definition.expr)
        if depth > config.max_expr_depth_per_definition:
            issues.append(
                issue(
                    "definition_expr_depth_exceeded",
                    f"definition expression depth {depth} exceeds limit {config.max_expr_depth_per_definition}",
                    f"{def_path}.expr",
                )
            )

        for ref_name in collect_var_refs(definition.expr):
            if ref_name in all_names and ref_name not in defined_names:
                issues.append(
                    issue(
                        "forward_var_ref",
                        f"variable {ref_name} is referenced before definition",
                        f"{def_path}.expr",
                    )
                )
            elif ref_name not in all_names:
                issues.append(
                    issue(
                        "undefined_var_ref",
                        f"variable {ref_name} is not defined",
                        f"{def_path}.expr",
                    )
                )
        defined_names.add(name)

    return_depth = compute_expr_depth(plan.return_expr)
    if return_depth > config.max_return_expr_depth:
        issues.append(
            issue(
                "return_expr_depth_exceeded",
                f"return expression depth {return_depth} exceeds limit {config.max_return_expr_depth}",
                "return_expr",
            )
        )

    total_nodes = sum(count_expr_nodes(definition.expr) for definition in definitions) + count_expr_nodes(plan.return_expr)
    if total_nodes > config.max_total_expr_nodes:
        issues.append(
            issue(
                "total_expr_nodes_exceeded",
                f"total expression nodes {total_nodes} exceeds limit {config.max_total_expr_nodes}",
                "program",
            )
        )

    total_if_nodes = sum(count_if_nodes(definition.expr) for definition in definitions) + count_if_nodes(plan.return_expr)
    if total_if_nodes > config.max_if_nodes_total:
        issues.append(
            issue(
                "total_if_nodes_exceeded",
                f"total if nodes {total_if_nodes} exceeds limit {config.max_if_nodes_total}",
                "program",
            )
        )

    for ref_name in collect_var_refs(plan.return_expr):
        if ref_name not in seen_names:
            issues.append(
                issue(
                    "undefined_var_ref",
                    f"variable {ref_name} is not defined",
                    "return_expr",
                )
            )

    cycles = detect_definition_cycles(plan)
    for cycle in cycles:
        issues.append(
            issue(
                "definition_cycle",
                f"definition cycle detected: {' -> '.join(cycle)}",
                "definitions",
            )
        )

    return _dedupe_issues(issues)


def validate_program_plan_semantics(
    plan: ProgramPlan,
    env: FilteredEnvironment,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, definition in enumerate(plan.definitions):
        if isinstance(definition, VariableDefinitionNode):
            issues.extend(_validate_expr_semantics(definition.expr, env, f"definitions[{index}].expr"))
    issues.extend(_validate_expr_semantics(plan.return_expr, env, "return_expr"))
    return _dedupe_issues(issues)


def _validate_expr_semantics(
    expr: ExprPlanNode,
    env: FilteredEnvironment,
    path: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    registry = env.registry
    filtered_contexts = set(env.selected_global_context_ids) | set(env.selected_local_context_ids)
    filtered_globals = set(env.selected_global_context_ids)
    filtered_locals = set(env.selected_local_context_ids)
    filtered_bos = set(env.selected_bo_ids)
    filtered_functions = set(env.selected_function_ids)

    if isinstance(expr, ContextRefPlanNode):
        context_id = _resolve_context_id(expr.path, env, allowed_ids=filtered_globals | filtered_locals)
        if context_id is None:
            issues.append(issue("unknown_context_ref", f"unknown context ref: {expr.path}", path))
        elif context_id not in filtered_contexts:
            issues.append(issue("context_not_in_filtered_environment", f"context not in filtered environment: {expr.path}", path))
        return issues

    if isinstance(expr, LocalRefPlanNode):
        context_id = _resolve_context_id(expr.path, env, allowed_ids=filtered_locals)
        if context_id is None:
            issues.append(issue("unknown_local_ref", f"unknown local ref: {expr.path}", path))
        elif context_id not in filtered_locals:
            issues.append(issue("local_not_in_filtered_environment", f"local ref not in filtered environment: {expr.path}", path))
        return issues

    if isinstance(expr, QueryCallPlanNode):
        if expr.query_kind in {"select", "select_one"}:
            bo_id, bo = _resolve_bo(expr, env)
            if bo is None or bo_id is None:
                issues.append(issue("unknown_bo_ref", f"unknown BO ref: {expr.source_name}", path))
            else:
                if bo_id not in filtered_bos:
                    issues.append(issue("bo_not_in_filtered_environment", f"bo not in filtered environment: {bo_id}", path))
                if expr.filter_expr is not None:
                    issues.extend(_validate_where_expr(expr.filter_expr, bo, env, f"{path}.filter_expr"))
        elif expr.query_kind in {"fetch", "fetch_one"}:
            resolved_matches = _resolve_naming_sql_matches(expr, env)
            if not resolved_matches:
                issues.append(
                    issue(
                        "unknown_naming_sql",
                        f"unknown naming sql for query: {expr.source_name}",
                        f"{path}.source_name",
                    )
                )
            elif len(resolved_matches) > 1:
                issues.append(
                    issue(
                        "ambiguous_naming_sql",
                        f"ambiguous naming sql for query: {expr.source_name}",
                        f"{path}.source_name",
                    )
                )
            else:
                resolved_bo_id, resolved_bo, naming_sql = resolved_matches[0]
                if resolved_bo_id not in filtered_bos:
                    issues.append(issue("bo_not_in_filtered_environment", f"bo not in filtered environment: {resolved_bo_id}", path))
                actual_keys = [pair.param_name for pair in expr.params if str(pair.param_name or "").strip()]
                expected_params = list(getattr(naming_sql, "params", []) or [])
                expected = [str(getattr(item, "param_name", "") or "").strip() for item in expected_params if str(getattr(item, "param_name", "") or "").strip()]
                if set(expected) != set(actual_keys) or len(expected) != len(actual_keys):
                    issues.append(
                        issue(
                            "naming_sql_param_mismatch",
                            f"naming sql params mismatch for {getattr(naming_sql, 'naming_sql_name', '')}: expected={expected}, actual={actual_keys}",
                            f"{path}.params",
                        )
                    )
                expected_map = {str(getattr(param, "param_name", "") or ""): param for param in expected_params}
                actual_pairs_by_name = {str(pair.param_name or ""): pair for pair in expr.params if str(pair.param_name or "").strip()}
                for expected_name, expected_param in expected_map.items():
                    expected_ref = getattr(expected_param, "normalized_type_ref", None)
                    if expected_ref is None:
                        issues.append(
                            issue(
                                "naming_sql_param_signature_missing",
                                f"naming sql param signature missing for {getattr(naming_sql, 'naming_sql_name', '')}.{expected_name}",
                                f"{path}.params",
                                severity="warning",
                            )
                        )
                        continue
                    if not getattr(expected_ref, "data_type", ""):
                        issues.append(
                            issue(
                                "naming_sql_param_data_type_missing",
                                f"naming sql expected data_type missing for {getattr(naming_sql, 'naming_sql_name', '')}.{expected_name}",
                                f"{path}.params",
                                severity="warning",
                            )
                        )
                    if not getattr(expected_ref, "data_type_name", ""):
                        issues.append(
                            issue(
                                "naming_sql_param_data_type_name_missing",
                                f"naming sql expected data_type_name missing for {getattr(naming_sql, 'naming_sql_name', '')}.{expected_name}",
                                f"{path}.params",
                                severity="warning",
                            )
                        )
                    if getattr(expected_ref, "is_list", None) is None:
                        issues.append(
                            issue(
                                "naming_sql_param_is_list_missing",
                                f"naming sql expected is_list missing for {getattr(naming_sql, 'naming_sql_name', '')}.{expected_name}",
                                f"{path}.params",
                                severity="warning",
                            )
                        )
                    actual_pair = actual_pairs_by_name.get(expected_name)
                    if actual_pair is None:
                        continue
                    actual_type = _infer_naming_sql_expr_type(actual_pair.value_expr, env)
                    if getattr(actual_type, "is_unknown", True):
                        issues.append(
                            issue(
                                "naming_sql_param_actual_type_unresolved",
                                f"naming sql actual type unresolved for {getattr(naming_sql, 'naming_sql_name', '')}.{expected_name}",
                                f"{path}.params",
                                severity="warning",
                            )
                        )
                        continue
                    match_result = compare_namingsql_param_type(expected_ref, actual_type)
                    if not match_result.matched:
                        issues.append(
                            issue(
                                "naming_sql_param_type_mismatch",
                                (
                                    f"naming sql param type mismatch for {getattr(naming_sql, 'naming_sql_name', '')}.{expected_name}: "
                                    f"{match_result.reason}"
                                ),
                                f"{path}.params",
                            )
                        )
        else:
            issues.append(issue("invalid_query_shape", f"unsupported query kind: {expr.query_kind}", f"{path}.query_kind"))
        if expr.filter_expr is not None:
            issues.extend(_validate_expr_semantics(expr.filter_expr, env, f"{path}.filter_expr"))
        for pair_index, pair in enumerate(expr.params):
            issues.extend(_validate_expr_semantics(pair.value_expr, env, f"{path}.params[{pair_index}].value_expr"))
        return issues

    if isinstance(expr, FunctionCallPlanNode):
        function_id, function = _resolve_function(expr, env)
        if function is None or function_id is None:
            issues.append(issue("unknown_function_ref", f"unknown function ref: {expr.function_name}", path))
        else:
            if function_id not in filtered_functions:
                issues.append(issue("function_not_in_filtered_environment", f"function not in filtered environment: {function_id}", path))
            if function.params and len(expr.args) != len(function.params):
                issues.append(
                    issue(
                        "function_args_mismatch",
                        f"function args mismatch: {function_id} expected {len(function.params)} got {len(expr.args)}",
                        f"{path}.args",
                    )
                )
            param_defs = list(getattr(function, "param_defs", []) or [])
            if param_defs:
                for arg_index, expected in enumerate(param_defs):
                    if arg_index >= len(expr.args):
                        break
                    if expected.normalized_param_type == "unknown":
                        issues.append(
                            issue(
                                "function_param_type_unknown",
                                f"function param type unresolved: {function_id}.{expected.param_name}",
                                f"{path}.args[{arg_index}]",
                                severity="warning",
                            )
                        )
                        continue
                    actual_ref = _infer_expr_type(expr.args[arg_index], env)
                    if actual_ref.normalized_type == "unknown":
                        issues.append(
                            issue(
                                "function_arg_type_unresolved",
                                f"function arg type unresolved for {function_id}.{expected.param_name}",
                                f"{path}.args[{arg_index}]",
                                severity="warning",
                            )
                        )
                        continue
                    if expected.normalized_param_type != actual_ref.normalized_type:
                        issues.append(
                            issue(
                                "function_arg_type_mismatch",
                                f"function arg type mismatch for {function_id}.{expected.param_name}: expected={expected.normalized_param_type}, actual={actual_ref.normalized_type}",
                                f"{path}.args[{arg_index}]",
                            )
                        )
        for arg_index, argument in enumerate(expr.args):
            issues.extend(_validate_expr_semantics(argument, env, f"{path}.args[{arg_index}]"))
        return issues

    if isinstance(expr, IfPlanNode):
        issues.extend(_validate_expr_semantics(expr.condition, env, f"{path}.condition"))
        issues.extend(_validate_expr_semantics(expr.then_expr, env, f"{path}.then_expr"))
        issues.extend(_validate_expr_semantics(expr.else_expr, env, f"{path}.else_expr"))
        return issues

    if isinstance(expr, BinaryOpPlanNode):
        issues.extend(_validate_expr_semantics(expr.left, env, f"{path}.left"))
        issues.extend(_validate_expr_semantics(expr.right, env, f"{path}.right"))
        return issues

    if isinstance(expr, UnaryOpPlanNode):
        issues.extend(_validate_expr_semantics(expr.operand, env, f"{path}.operand"))
        return issues

    if isinstance(expr, FieldAccessPlanNode):
        issues.extend(_validate_expr_semantics(expr.base, env, f"{path}.base"))
        return issues

    if isinstance(expr, IndexAccessPlanNode):
        issues.extend(_validate_expr_semantics(expr.base, env, f"{path}.base"))
        issues.extend(_validate_expr_semantics(expr.index, env, f"{path}.index"))
        return issues

    if isinstance(expr, ListLiteralPlanNode):
        for item_index, item in enumerate(expr.items):
            issues.extend(_validate_expr_semantics(item, env, f"{path}.items[{item_index}]"))
        return issues

    if isinstance(expr, (LiteralPlanNode, VarRefPlanNode)):
        return issues

    return issues


def compute_expr_depth(node: ExprPlanNode) -> int:
    children = _child_expressions(node)
    if not children:
        return 1
    return 1 + max(compute_expr_depth(child) for child in children)


def count_expr_nodes(node: ExprPlanNode) -> int:
    return 1 + sum(count_expr_nodes(child) for child in _child_expressions(node))


def count_if_nodes(node: ExprPlanNode) -> int:
    current = 1 if isinstance(node, IfPlanNode) else 0
    return current + sum(count_if_nodes(child) for child in _child_expressions(node))


def collect_var_refs(node: ExprPlanNode) -> list[str]:
    refs: list[str] = []
    if isinstance(node, VarRefPlanNode):
        refs.append(node.name)
    for child in _child_expressions(node):
        refs.extend(collect_var_refs(child))
    return refs


def collect_context_refs(node: ExprPlanNode) -> list[str]:
    refs: list[str] = []
    if isinstance(node, ContextRefPlanNode):
        refs.append(node.path)
    for child in _child_expressions(node):
        refs.extend(collect_context_refs(child))
    return refs


def collect_local_refs(node: ExprPlanNode) -> list[str]:
    refs: list[str] = []
    if isinstance(node, LocalRefPlanNode):
        refs.append(node.path)
    for child in _child_expressions(node):
        refs.extend(collect_local_refs(child))
    return refs


def collect_query_refs(node: ExprPlanNode) -> list[QueryCallPlanNode]:
    refs: list[QueryCallPlanNode] = []
    if isinstance(node, QueryCallPlanNode):
        refs.append(node)
    for child in _child_expressions(node):
        refs.extend(collect_query_refs(child))
    return refs


def collect_function_refs(node: ExprPlanNode) -> list[FunctionCallPlanNode]:
    refs: list[FunctionCallPlanNode] = []
    if isinstance(node, FunctionCallPlanNode):
        refs.append(node)
    for child in _child_expressions(node):
        refs.extend(collect_function_refs(child))
    return refs


def build_definition_dependency_graph(plan: ProgramPlan) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    definition_names = {definition.name for definition in plan.definitions if hasattr(definition, "name")}
    for definition in plan.definitions:
        if isinstance(definition, VariableDefinitionNode):
            graph[definition.name] = {ref for ref in collect_var_refs(definition.expr) if ref in definition_names}
    return graph


def detect_definition_cycles(plan: ProgramPlan) -> list[list[str]]:
    graph = build_definition_dependency_graph(plan)
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            cycle_start = visiting.index(name)
            cycles.append(visiting[cycle_start:] + [name])
            return
        if name in visited:
            return
        visiting.append(name)
        for dependency in graph.get(name, set()):
            visit(dependency)
        visiting.pop()
        visited.add(name)

    for name in graph:
        visit(name)
    return cycles


def _child_expressions(node: ExprPlanNode) -> list[ExprPlanNode]:
    if isinstance(node, FunctionCallPlanNode):
        return list(node.args)
    if isinstance(node, QueryCallPlanNode):
        children = []
        if node.filter_expr is not None:
            children.append(node.filter_expr)
        children.extend([pair.value_expr for pair in node.params])
        return children
    if isinstance(node, IfPlanNode):
        return [node.condition, node.then_expr, node.else_expr]
    if isinstance(node, BinaryOpPlanNode):
        return [node.left, node.right]
    if isinstance(node, UnaryOpPlanNode):
        return [node.operand]
    if isinstance(node, FieldAccessPlanNode):
        return [node.base]
    if isinstance(node, IndexAccessPlanNode):
        return [node.base, node.index]
    if isinstance(node, ListLiteralPlanNode):
        return list(node.items)
    return []


def _resolve_context_id(ref: str, env: FilteredEnvironment, allowed_ids: set[str] | None = None) -> str | None:
    local_set = env.visible_local_context
    if ref in local_set.nodes_by_id and (allowed_ids is None or ref in allowed_ids):
        return ref
    local_by_name = local_set.nodes_by_property_name.get(ref.removeprefix("$local$."))
    if local_by_name is not None and local_by_name.access_path == ref:
        if allowed_ids is None or local_by_name.resource_id in allowed_ids:
            return local_by_name.resource_id

    registry = env.registry
    if ref in registry.contexts:
        if allowed_ids is None or ref in allowed_ids:
            return ref
    aliases = _context_ref_aliases(ref)
    for context_id, context in registry.contexts.items():
        if context.path in aliases and (allowed_ids is None or context_id in allowed_ids):
            return context_id
    return None


def _resolve_bo(expr: QueryCallPlanNode, env: FilteredEnvironment) -> tuple[str | None, Any | None]:
    registry = env.registry
    if expr.bo_id and expr.bo_id in registry.bos:
        return expr.bo_id, registry.bos[expr.bo_id]
    if expr.source_name and expr.source_name in registry.bos:
        return expr.source_name, registry.bos[expr.source_name]
    for bo_id, bo in registry.bos.items():
        if bo.bo_name == expr.source_name:
            return bo_id, bo
    return None, None


def _resolve_function(expr: FunctionCallPlanNode, env: FilteredEnvironment) -> tuple[str | None, Any | None]:
    registry = env.registry
    if expr.function_id and expr.function_id in registry.functions:
        return expr.function_id, registry.functions[expr.function_id]
    if expr.function_name and expr.function_name in registry.functions:
        return expr.function_name, registry.functions[expr.function_name]
    for function_id, function in registry.functions.items():
        if function.full_name == expr.function_name or function.name == expr.function_name:
            return function_id, function
    return None, None


def _infer_expr_type(expr: ExprPlanNode, env: FilteredEnvironment) -> Any:
    if isinstance(expr, LiteralPlanNode):
        value = expr.value
        if isinstance(value, bool):
            return normalize_function_type("boolean")
        if isinstance(value, int) and not isinstance(value, bool):
            return normalize_function_type("int")
        if isinstance(value, float):
            return normalize_function_type("double")
        if isinstance(value, str):
            return normalize_function_type("string")
        return normalize_function_type(None)
    if isinstance(expr, ListLiteralPlanNode):
        if not expr.items:
            return normalize_function_type("list[unknown]")
        first_type = _infer_expr_type(expr.items[0], env)
        if first_type.normalized_type == "unknown":
            return normalize_function_type("list[unknown]")
        return normalize_function_type(f"list[{first_type.normalized_type}]")
    if isinstance(expr, FunctionCallPlanNode):
        _, fn = _resolve_function(expr, env)
        if fn is not None and getattr(fn, "return_type", ""):
            return normalize_function_type(getattr(fn, "return_type_raw", "") or getattr(fn, "return_type", ""))
    return normalize_function_type(None)


def _bo_has_field(bo: Any, field_name: str) -> bool:
    return any(_field_name_from_identifier(field_id) == field_name or field_id == field_name for field_id in bo.field_ids)


def _bo_has_naming_sql(bo: Any, naming_sql: str) -> bool:
    candidate_names = {str(naming_sql or "").strip(), _suffix_name(str(naming_sql or "").strip())}
    bo_ids = set(getattr(bo, "naming_sql_ids", []) or [])
    if any(sql_id in candidate_names or _suffix_name(sql_id) in candidate_names for sql_id in bo_ids):
        return True
    name_by_key = dict(getattr(bo, "naming_sql_name_by_key", {}) or {})
    if any(str(key) in candidate_names or str(value) in candidate_names for key, value in name_by_key.items()):
        return True
    return False


def _resolve_naming_sql_matches(expr: QueryCallPlanNode, env: FilteredEnvironment) -> list[tuple[str, Any, Any]]:
    matches: list[tuple[str, Any, Any]] = []
    bo_id, bo = _resolve_bo(expr, env)
    if bo is not None and bo_id is not None:
        result = _resolve_naming_sql_for_bo(bo, expr)
        if result is not None:
            matches.append((bo_id, bo, result))
        return matches

    for each_bo_id, each_bo in env.registry.bos.items():
        result = _resolve_naming_sql_for_bo(each_bo, expr)
        if result is not None:
            matches.append((each_bo_id, each_bo, result))
    return matches


def _resolve_naming_sql_for_bo(bo: Any, expr: QueryCallPlanNode) -> Any | None:
    candidate_keys = [
        str(expr.naming_sql_id or "").strip(),
        str(expr.source_name or "").strip(),
    ]
    for key in candidate_keys:
        if not key:
            continue
        naming_sql_id = bo.naming_sql_name_by_key.get(key)
        if isinstance(getattr(bo, "naming_sqls_by_id", None), dict):
            sql_def = bo.naming_sqls_by_id.get(key)
            if sql_def is not None:
                return sql_def
            if naming_sql_id and naming_sql_id in bo.naming_sqls_by_id:
                return bo.naming_sqls_by_id[naming_sql_id]
            for each_def in getattr(bo, "naming_sqls", []) or []:
                if getattr(each_def, "naming_sql_name", "") == key:
                    return each_def
        naming_sql_name = bo.naming_sql_name_by_key.get(key)
        if naming_sql_name:
            param_names = bo.naming_sql_param_names_by_key.get(key) or bo.naming_sql_param_names_by_key.get(naming_sql_name) or []
            return None
    return None


def _infer_naming_sql_expr_type(expr: ExprPlanNode, env: FilteredEnvironment) -> Any:
    inferred = _infer_expr_type(expr, env)
    normalized = str(getattr(inferred, "normalized_type", "") or "").lower()
    if normalized == "unknown":
        return _naming_type_ref("", "", None, is_unknown=True)
    if normalized.startswith("list["):
        item_type = normalized[len("list[") : -1]
        data_type_name = _map_basic_data_type_name(item_type)
        return _naming_type_ref("basic", data_type_name, True, is_unknown=not bool(data_type_name))
    data_type_name = _map_basic_data_type_name(normalized)
    return _naming_type_ref("basic", data_type_name, False, is_unknown=not bool(data_type_name))


def _map_basic_data_type_name(normalized_type: str) -> str:
    mapping = {
        "string": "String",
        "int": "INT64",
        "double": "Double",
        "boolean": "Boolean",
    }
    return mapping.get(str(normalized_type or "").lower(), "")


def _naming_type_ref(data_type: str, data_type_name: str, is_list: bool | None, is_unknown: bool) -> Any:
    class _TypeRef:
        def __init__(self):
            self.data_type = data_type
            self.data_type_name = data_type_name
            self.is_list = is_list
            self.is_unknown = is_unknown

    return _TypeRef()


def compare_namingsql_param_type(expected: Any, actual: Any) -> NamingSQLParamTypeMatchResult:
    expected_data_type = str(getattr(expected, "data_type", "") or "")
    actual_data_type = str(getattr(actual, "data_type", "") or "")
    if expected_data_type and expected_data_type != actual_data_type:
        return NamingSQLParamTypeMatchResult(
            matched=False,
            mismatch_stage="data_type",
            reason=f"data_type mismatch expected={expected_data_type} actual={actual_data_type}",
        )

    expected_data_type_name = str(getattr(expected, "data_type_name", "") or "")
    actual_data_type_name = str(getattr(actual, "data_type_name", "") or "")
    if expected_data_type_name and expected_data_type_name != actual_data_type_name:
        return NamingSQLParamTypeMatchResult(
            matched=False,
            mismatch_stage="data_type_name",
            reason=f"data_type_name mismatch expected={expected_data_type_name} actual={actual_data_type_name}",
        )

    expected_is_list = getattr(expected, "is_list", None)
    actual_is_list = getattr(actual, "is_list", None)
    if expected_is_list is not None and expected_is_list != actual_is_list:
        return NamingSQLParamTypeMatchResult(
            matched=False,
            mismatch_stage="is_list",
            reason=f"is_list mismatch expected={expected_is_list} actual={actual_is_list}",
        )

    return NamingSQLParamTypeMatchResult(matched=True)


def _validate_where_expr(expr: ExprPlanNode, bo: Any, env: FilteredEnvironment, path: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(expr, BinaryOpPlanNode):
        operator = str(expr.operator or "").lower()
        logical_ops = {"and", "or"}
        compare_ops = {"==", "!=", ">", ">=", "<", "<="}
        if operator not in logical_ops | compare_ops:
            issues.append(issue("invalid_where_operator", f"unsupported where operator: {expr.operator}", f"{path}.operator"))
        if operator in logical_ops:
            issues.extend(_validate_where_expr(expr.left, bo, env, f"{path}.left"))
            issues.extend(_validate_where_expr(expr.right, bo, env, f"{path}.right"))
        else:
            issues.extend(_validate_expr_semantics(expr.left, env, f"{path}.left"))
            issues.extend(_validate_expr_semantics(expr.right, env, f"{path}.right"))
        return issues
    if isinstance(expr, UnaryOpPlanNode):
        if str(expr.operator or "").lower() != "not":
            issues.append(issue("invalid_where_operator", f"unsupported where unary operator: {expr.operator}", f"{path}.operator"))
        issues.extend(_validate_where_expr(expr.operand, bo, env, f"{path}.operand"))
        return issues
    if isinstance(expr, ContextRefPlanNode):
        context_id = _resolve_context_id(expr.path, env)
        if context_id is None:
            issues.append(issue("unknown_context_ref", f"unknown context ref: {expr.path}", path))
        return issues
    if isinstance(expr, LocalRefPlanNode):
        context_id = _resolve_context_id(expr.path, env)
        if context_id is None:
            issues.append(issue("unknown_local_ref", f"unknown local ref: {expr.path}", path))
        return issues
    if isinstance(expr, (LiteralPlanNode, VarRefPlanNode)):
        return issues
    if isinstance(expr, FieldAccessPlanNode):
        if expr.field and not _bo_has_field(bo, expr.field):
            issues.append(issue("unknown_bo_field", f"unknown BO field: {expr.field}", f"{path}.field"))
        issues.extend(_validate_expr_semantics(expr.base, env, f"{path}.base"))
        return issues
    issues.extend(_validate_expr_semantics(expr, env, path))
    return issues


def _field_name_from_identifier(value: str) -> str:
    return _suffix_name(value)


def _suffix_name(value: str) -> str:
    return value.split(":")[-1] if value else value


def _context_ref_aliases(ref: str) -> set[str]:
    aliases = {ref}
    if ref.startswith("$ctx$.root."):
        aliases.add("$ctx$." + ref[len("$ctx$.root.") :])
    elif ref.startswith("$ctx$."):
        aliases.add("$ctx$.root." + ref[len("$ctx$.") :])
    return aliases


def _dedupe_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[ValidationIssue] = []
    for current in issues:
        key = (current.code, current.message, current.path, current.severity)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(current)
    return deduped


def _plans_equivalent(left: ProgramPlan, right: ProgramPlan) -> bool:
    return left.model_dump(mode="python", exclude={"raw_plan"}) == right.model_dump(mode="python", exclude={"raw_plan"})


def parse_program_plan_payload(raw: dict[str, Any]) -> ProgramPlan:
    data = dict(raw)
    if isinstance(data.get("raw_plan"), str):
        try:
            data["raw_plan"] = json.loads(data["raw_plan"])
        except json.JSONDecodeError:
            data["raw_plan"] = {"raw": data["raw_plan"]}
    if "raw_plan" not in data:
        data["raw_plan"] = raw
    return ProgramPlan.model_validate(data)
