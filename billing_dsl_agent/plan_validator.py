from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from billing_dsl_agent.models import (
    BinaryOpPlanNode,
    ContextRefPlanNode,
    DefinitionNode,
    ExprPlanNode,
    FilteredEnvironment,
    FunctionCallPlanNode,
    IfPlanNode,
    IndexAccessPlanNode,
    LegacyPlanDraft,
    ListLiteralPlanNode,
    LocalRefPlanNode,
    MethodDefinitionNode,
    ProgramPlan,
    ProgramPlanLimits,
    QueryCallPlanNode,
    QueryFilterPlanNode,
    QueryPairPlanNode,
    UnaryOpPlanNode,
    ValidationIssue,
    ValidationResult,
    VarRefPlanNode,
    VariableDefinitionNode,
    FieldAccessPlanNode,
    LiteralPlanNode,
)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED_WORDS = {"def", "return", "if", "else", "and", "or", "not"}


@dataclass(slots=True)
class NamingSQLParamTypeMatchResult:
    is_match: bool
    stage: str
    reason: str = ""


def compare_namingsql_param_type(expected: dict[str, Any], actual: dict[str, Any]) -> NamingSQLParamTypeMatchResult:
    expected_data_type = str(expected.get("data_type") or "").strip()
    actual_data_type = str(actual.get("data_type") or "").strip()
    if expected_data_type != actual_data_type:
        return NamingSQLParamTypeMatchResult(
            is_match=False,
            stage="data_type",
            reason=f"data_type mismatch: expected={expected_data_type} actual={actual_data_type}",
        )

    expected_data_type_name = str(expected.get("data_type_name") or "").strip()
    actual_data_type_name = str(actual.get("data_type_name") or "").strip()
    if expected_data_type_name != actual_data_type_name:
        return NamingSQLParamTypeMatchResult(
            is_match=False,
            stage="data_type_name",
            reason=f"data_type_name mismatch: expected={expected_data_type_name} actual={actual_data_type_name}",
        )

    expected_is_list = expected.get("is_list")
    actual_is_list = actual.get("is_list")
    if expected_is_list != actual_is_list:
        return NamingSQLParamTypeMatchResult(
            is_match=False,
            stage="is_list",
            reason=f"is_list mismatch: expected={expected_is_list} actual={actual_is_list}",
        )
    return NamingSQLParamTypeMatchResult(is_match=True, stage="matched", reason="")


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
        while True:
            issues = self._collect_issues(current, env)
            if not issues:
                return ValidationResult(is_valid=True, issues=[], repaired_plan=current)
            if self.planner is None or attempts >= self.max_retries:
                return ValidationResult(is_valid=False, issues=issues, repaired_plan=current)
            repaired = self.planner.repair(current, env, issues)
            if repaired is None:
                return ValidationResult(is_valid=False, issues=issues, repaired_plan=current)
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
        if definition.kind == "method":
            issues.append(
                issue(
                    "unsupported_definition_kind",
                    "method definitions are not supported yet",
                    f"{def_path}.kind",
                )
            )
            continue

        assert isinstance(definition, VariableDefinitionNode)
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

    total_nodes = sum(
        count_expr_nodes(definition.expr) if isinstance(definition, VariableDefinitionNode) else count_expr_nodes(definition.body)
        for definition in definitions
    ) + count_expr_nodes(plan.return_expr)
    if total_nodes > config.max_total_expr_nodes:
        issues.append(
            issue(
                "total_expr_nodes_exceeded",
                f"total expression nodes {total_nodes} exceeds limit {config.max_total_expr_nodes}",
                "program",
            )
        )

    total_if_nodes = sum(
        count_if_nodes(definition.expr) if isinstance(definition, VariableDefinitionNode) else count_if_nodes(definition.body)
        for definition in definitions
    ) + count_if_nodes(plan.return_expr)
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
        elif isinstance(definition, MethodDefinitionNode):
            issues.extend(_validate_expr_semantics(definition.body, env, f"definitions[{index}].body"))
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
                issues.append(issue("unknown_bo_ref", f"unknown BO ref: {expr.bo_id or expr.source_name}", path))
            else:
                if bo_id not in filtered_bos:
                    issues.append(issue("bo_not_in_filtered_environment", f"bo not in filtered environment: {bo_id}", path))
                if expr.field and not _bo_has_field(bo, expr.field):
                    issues.append(issue("unknown_bo_field", f"unknown BO field: {expr.field}", f"{path}.field"))
                if expr.data_source and bo.data_source and expr.data_source != bo.data_source:
                    issues.append(issue("bo_data_source_mismatch", f"bo data source mismatch: {bo_id}", f"{path}.data_source"))
                if expr.naming_sql_id and not _bo_has_naming_sql(bo, expr.naming_sql_id):
                    issues.append(issue("unknown_naming_sql", f"unknown naming sql id: {expr.naming_sql_id}", f"{path}.naming_sql_id"))
                for filter_index, query_filter in enumerate(expr.filters):
                    if not _bo_has_field(bo, query_filter.field):
                        issues.append(
                            issue(
                                "unknown_bo_field",
                                f"unknown BO field: {query_filter.field}",
                                f"{path}.filters[{filter_index}].field",
                            )
                        )
                if expr.where is not None:
                    issues.extend(_validate_where_expr(expr.where, bo, env, f"{path}.where"))
        elif expr.query_kind in {"fetch", "fetch_one"}:
            resolved = _resolve_naming_sql(expr, env)
            if resolved is None:
                issues.append(
                    issue(
                        "unknown_naming_sql",
                        f"unknown naming sql for query: {expr.naming_sql_id or expr.source_name}",
                        f"{path}.naming_sql_id",
                    )
                )
            else:
                resolved_bo_id, resolved_bo, naming_sql_name, expected_param_defs = resolved
                if resolved_bo_id not in filtered_bos:
                    issues.append(issue("bo_not_in_filtered_environment", f"bo not in filtered environment: {resolved_bo_id}", path))
                if expr.data_source and resolved_bo.data_source and expr.data_source != resolved_bo.data_source:
                    issues.append(
                        issue("bo_data_source_mismatch", f"bo data source mismatch: {resolved_bo_id}", f"{path}.data_source")
                    )
                actual_keys = [pair.key for pair in expr.pairs if str(pair.key or "").strip()]
                if not actual_keys and expr.filters:
                    actual_keys = [flt.field for flt in expr.filters if str(flt.field or "").strip()]
                expected = [str(item.get("param_name") or "").strip() for item in expected_param_defs if str(item.get("param_name") or "").strip()]
                if set(expected) != set(actual_keys) or len(expected) != len(actual_keys):
                    issues.append(
                        issue(
                            "naming_sql_param_mismatch",
                            f"naming sql params mismatch for {naming_sql_name}: expected={expected}, actual={actual_keys}",
                            f"{path}.pairs",
                        )
                    )
                for expected_index, expected_param in enumerate(expected_param_defs):
                    param_name = str(expected_param.get("param_name") or "").strip()
                    if not param_name:
                        continue
                    if not str(expected_param.get("data_type") or "").strip():
                        issues.append(
                            issue(
                                "naming_sql_param_signature_incomplete",
                                f"expected naming sql param missing data_type: {param_name}",
                                f"{path}.signature[{expected_index}]",
                                severity="warning",
                            )
                        )
                    if not str(expected_param.get("data_type_name") or "").strip():
                        issues.append(
                            issue(
                                "naming_sql_param_signature_incomplete",
                                f"expected naming sql param missing data_type_name: {param_name}",
                                f"{path}.signature[{expected_index}]",
                                severity="warning",
                            )
                        )
                    if not isinstance(expected_param.get("is_list"), bool):
                        issues.append(
                            issue(
                                "naming_sql_param_signature_incomplete",
                                f"expected naming sql param missing is_list: {param_name}",
                                f"{path}.signature[{expected_index}]",
                                severity="warning",
                            )
                        )
                actual_pair_map = {str(pair.key or "").strip(): pair for pair in expr.pairs if str(pair.key or "").strip()}
                for expected_index, expected_param in enumerate(expected_param_defs):
                    expected_name = str(expected_param.get("param_name") or "").strip()
                    if not expected_name:
                        continue
                    pair = actual_pair_map.get(expected_name)
                    if pair is None:
                        continue
                    actual_type = _extract_actual_param_type_from_expr(pair.value)
                    if actual_type is None:
                        issues.append(
                            issue(
                                "naming_sql_actual_type_unavailable",
                                f"actual naming sql param type unavailable: {expected_name}",
                                f"{path}.pairs[{expected_index}]",
                                severity="warning",
                            )
                        )
                        continue
                    match = compare_namingsql_param_type(expected_param, actual_type)
                    if not match.is_match:
                        issues.append(
                            issue(
                                "naming_sql_param_type_mismatch",
                                f"{expected_name} {match.reason}",
                                f"{path}.pairs[{expected_index}]",
                            )
                        )
        else:
            issues.append(issue("invalid_query_shape", f"unsupported query kind: {expr.query_kind}", f"{path}.query_kind"))
        for filter_index, query_filter in enumerate(expr.filters):
            issues.extend(
                _validate_expr_semantics(
                    query_filter.value,
                    env,
                    f"{path}.filters[{filter_index}].value",
                )
            )
        for pair_index, pair in enumerate(expr.pairs):
            issues.extend(_validate_expr_semantics(pair.value, env, f"{path}.pairs[{pair_index}].value"))
        return issues

    if isinstance(expr, FunctionCallPlanNode):
        function_id, function = _resolve_function(expr, env)
        if function is None or function_id is None:
            issues.append(issue("unknown_function_ref", f"unknown function ref: {expr.function_id or expr.function_name}", path))
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
        elif isinstance(definition, MethodDefinitionNode):
            graph[definition.name] = {ref for ref in collect_var_refs(definition.body) if ref in definition_names}
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


def adapt_legacy_plan(raw_plan: LegacyPlanDraft | dict[str, Any]) -> ProgramPlan:
    raw_dict = raw_plan.model_dump(mode="python") if isinstance(raw_plan, LegacyPlanDraft) else dict(raw_plan)
    if "expr_tree" in raw_dict:
        expr_payload = _normalize_legacy_expr_tree(raw_dict["expr_tree"])
        return ProgramPlan.model_validate(
            {
                "definitions": [],
                "return_expr": expr_payload,
                "raw_plan": raw_dict.get("raw_plan") or raw_dict,
            }
        )

    legacy = raw_plan if isinstance(raw_plan, LegacyPlanDraft) else LegacyPlanDraft.model_validate(raw_dict)
    return ProgramPlan(
        definitions=[],
        return_expr=_legacy_plan_to_expr(legacy),
        raw_plan=legacy.raw_plan or raw_dict,
        legacy_plan=legacy,
    )


def _legacy_plan_to_expr(plan: LegacyPlanDraft) -> ExprPlanNode:
    pattern = plan.expression_pattern
    if pattern == "if":
        cond_ref = str(plan.semantic_slots.get("condition_ref") or (plan.context_refs[0] if plan.context_refs else ""))
        return IfPlanNode(
            type="if",
            condition=BinaryOpPlanNode(
                type="binary_op",
                operator=str(plan.semantic_slots.get("condition_operator") or "=="),
                left=_legacy_scalar_to_expr(cond_ref),
                right=LiteralPlanNode(type="literal", value=plan.semantic_slots.get("condition_value")),
            ),
            then_expr=LiteralPlanNode(type="literal", value=plan.semantic_slots.get("true_output")),
            else_expr=LiteralPlanNode(type="literal", value=plan.semantic_slots.get("false_output")),
        )

    if pattern in {"select", "select_one", "fetch", "fetch_one"} and plan.bo_refs:
        bo_ref = plan.bo_refs[0]
        bo_id = str(bo_ref.get("bo_id") or "").strip() or None
        field_id = str(bo_ref.get("field_id") or "").strip()
        naming_sql_id = str(bo_ref.get("naming_sql_id") or "").strip() or None
        source_name = _bo_name_from_identifier(bo_id or "")
        if pattern in {"fetch", "fetch_one"} and naming_sql_id:
            source_name = _suffix_name(naming_sql_id)
        return QueryCallPlanNode(
            type="query_call",
            query_kind=pattern,
            source_name=source_name,
            field=_field_name_from_identifier(field_id) if field_id else None,
            bo_id=bo_id,
            data_source=str(bo_ref.get("data_source") or "").strip() or None,
            naming_sql_id=naming_sql_id,
            filters=[
                QueryFilterPlanNode(
                    field=str(param.get("param_name") or "").strip(),
                    value=_legacy_param_to_expr(param),
                )
                for param in bo_ref.get("params") or []
            ],
            pairs=[
                QueryPairPlanNode(
                    key=str(param.get("param_name") or "").strip(),
                    value=_legacy_param_to_expr(param),
                )
                for param in bo_ref.get("params") or []
            ],
        )

    if pattern == "function_call" and plan.function_refs:
        function_id = str(plan.function_refs[0] or "").strip() or None
        return FunctionCallPlanNode(
            type="function_call",
            function_name=_function_name_from_identifier(function_id or ""),
            function_id=function_id,
            args=[_legacy_scalar_to_expr(value) for value in plan.semantic_slots.get("function_args", [])],
        )

    if plan.context_refs:
        return _legacy_scalar_to_expr(plan.context_refs[0])

    return LiteralPlanNode(type="literal", value=plan.semantic_slots.get("literal"))


def _legacy_param_to_expr(param: dict[str, Any]) -> ExprPlanNode:
    source_type = str(param.get("value_source_type") or "").strip()
    value = param.get("value")
    if source_type == "constant":
        return LiteralPlanNode(type="literal", value=value)
    return _legacy_scalar_to_expr(value)


def _legacy_scalar_to_expr(value: Any) -> ExprPlanNode:
    if isinstance(value, dict):
        if "type" in value or "kind" in value:
            payload = _normalize_legacy_expr_tree(value)
            return _validate_expr_payload(payload)
        raise ValueError("unsupported legacy scalar dict")
    if isinstance(value, str):
        if value.startswith("context:"):
            return ContextRefPlanNode(type="context_ref", path=value.split("context:", 1)[1])
        if value.startswith("local:"):
            return LocalRefPlanNode(type="local_ref", path=value.split("local:", 1)[1])
        if value.startswith("$ctx$."):
            return ContextRefPlanNode(type="context_ref", path=value)
        if value.startswith("$local$."):
            return LocalRefPlanNode(type="local_ref", path=value)
    return LiteralPlanNode(type="literal", value=value)


def _normalize_legacy_expr_tree(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("expr_tree must be an object")
    if "type" in payload:
        node_type = str(payload.get("type") or "").strip()
        if node_type == "query_call":
            return {
                **payload,
                "filters": [
                    {
                        "field": item.get("field"),
                        "value": _normalize_legacy_expr_tree(item.get("value"))
                        if isinstance(item.get("value"), dict)
                        else _legacy_scalar_to_expr(item.get("value")).model_dump(mode="python"),
                    }
                    for item in payload.get("filters") or []
                ],
            }
        if node_type == "function_call":
            return {
                **payload,
                "args": [
                    _normalize_legacy_expr_tree(item) if isinstance(item, dict) else _legacy_scalar_to_expr(item).model_dump(mode="python")
                    for item in payload.get("args") or []
                ],
            }
        if node_type == "if":
            return {
                **payload,
                "condition": _normalize_legacy_expr_tree(payload.get("condition")),
                "then_expr": _normalize_legacy_expr_tree(payload.get("then_expr")),
                "else_expr": _normalize_legacy_expr_tree(payload.get("else_expr")),
            }
        if node_type == "binary_op":
            return {
                **payload,
                "left": _normalize_legacy_expr_tree(payload.get("left")),
                "right": _normalize_legacy_expr_tree(payload.get("right")),
            }
        if node_type == "unary_op":
            return {
                **payload,
                "operand": _normalize_legacy_expr_tree(payload.get("operand")),
            }
        if node_type == "field_access":
            return {
                **payload,
                "base": _normalize_legacy_expr_tree(payload.get("base")),
            }
        if node_type == "index_access":
            return {
                **payload,
                "base": _normalize_legacy_expr_tree(payload.get("base")),
                "index": _normalize_legacy_expr_tree(payload.get("index")),
            }
        if node_type == "list_literal":
            return {
                **payload,
                "items": [
                    _normalize_legacy_expr_tree(item) if isinstance(item, dict) else _legacy_scalar_to_expr(item).model_dump(mode="python")
                    for item in payload.get("items") or []
                ],
            }
        return payload
    kind = str(payload.get("kind") or "").strip().upper()
    children = payload.get("children") or []
    metadata = payload.get("metadata") or {}
    value = payload.get("value")

    if kind == "LITERAL":
        return {"type": "literal", "value": value}
    if kind == "CONTEXT_REF":
        return {"type": "context_ref", "path": value}
    if kind == "LOCAL_REF":
        return {"type": "local_ref", "path": value}
    if kind == "VAR_REF":
        return {"type": "var_ref", "name": value}
    if kind == "FUNCTION_CALL":
        return {
            "type": "function_call",
            "function_name": value,
            "args": [_normalize_legacy_expr_tree(child) for child in children],
        }
    if kind == "QUERY_CALL":
        params = metadata.get("params") or []
        filters = metadata.get("filters") or [
            {
                "field": param.get("param_name"),
                "value": _legacy_param_to_expr(param).model_dump(mode="python"),
            }
            for param in params
        ]
        return {
            "type": "query_call",
            "query_kind": metadata.get("query_kind") or metadata.get("query_mode") or "select",
            "source_name": value,
            "field": metadata.get("target_field") or metadata.get("field"),
            "bo_id": metadata.get("bo_id"),
            "data_source": metadata.get("data_source"),
            "naming_sql_id": metadata.get("naming_sql_id"),
            "filters": [
                {
                    "field": item.get("field"),
                    "value": _normalize_legacy_expr_tree(item.get("value")) if isinstance(item.get("value"), dict) else _legacy_scalar_to_expr(item.get("value")).model_dump(mode="python"),
                }
                for item in filters
            ],
            "where": _normalize_legacy_expr_tree(metadata.get("where")) if isinstance(metadata.get("where"), dict) else None,
            "pairs": [
                {
                    "key": item.get("key") or item.get("field"),
                    "value": _normalize_legacy_expr_tree(item.get("value"))
                    if isinstance(item.get("value"), dict)
                    else _legacy_scalar_to_expr(item.get("value")).model_dump(mode="python"),
                }
                for item in (metadata.get("pairs") or [])
                if isinstance(item, dict)
            ],
        }
    if kind == "IF_EXPR":
        return {
            "type": "if",
            "condition": _normalize_legacy_expr_tree(children[0]),
            "then_expr": _normalize_legacy_expr_tree(children[1]),
            "else_expr": _normalize_legacy_expr_tree(children[2]),
        }
    if kind == "BINARY_OP":
        return {
            "type": "binary_op",
            "operator": value,
            "left": _normalize_legacy_expr_tree(children[0]),
            "right": _normalize_legacy_expr_tree(children[1]),
        }
    if kind == "UNARY_OP":
        return {
            "type": "unary_op",
            "operator": value,
            "operand": _normalize_legacy_expr_tree(children[0]),
        }
    if kind == "FIELD_ACCESS":
        return {
            "type": "field_access",
            "base": _normalize_legacy_expr_tree(children[0]),
            "field": value,
        }
    if kind == "INDEX_ACCESS":
        return {
            "type": "index_access",
            "base": _normalize_legacy_expr_tree(children[0]),
            "index": _normalize_legacy_expr_tree(children[1]),
        }
    if kind == "LIST_LITERAL":
        return {
            "type": "list_literal",
            "items": [_normalize_legacy_expr_tree(child) for child in children],
        }
    raise ValueError(f"unsupported legacy expr_tree kind: {kind or '<empty>'}")


def _validate_expr_payload(payload: dict[str, Any]) -> ExprPlanNode:
    wrapper = ProgramPlan.model_validate({"definitions": [], "return_expr": payload})
    return wrapper.return_expr


def _child_expressions(node: ExprPlanNode) -> list[ExprPlanNode]:
    if isinstance(node, FunctionCallPlanNode):
        return list(node.args)
    if isinstance(node, QueryCallPlanNode):
        children = [query_filter.value for query_filter in node.filters]
        if node.where is not None:
            children.append(node.where)
        children.extend([pair.value for pair in node.pairs])
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
    registry = env.registry
    if ref in registry.contexts:
        if allowed_ids is None or ref in allowed_ids:
            return ref
    for context_id, context in registry.contexts.items():
        if context.path == ref and (allowed_ids is None or context_id in allowed_ids):
            return context_id
    return None


def _resolve_bo(expr: QueryCallPlanNode, env: FilteredEnvironment) -> tuple[str | None, Any | None]:
    registry = env.registry
    if expr.bo_id and expr.bo_id in registry.bos:
        return expr.bo_id, registry.bos[expr.bo_id]
    for bo_id, bo in registry.bos.items():
        if bo.bo_name == expr.source_name:
            return bo_id, bo
    return None, None


def _resolve_function(expr: FunctionCallPlanNode, env: FilteredEnvironment) -> tuple[str | None, Any | None]:
    registry = env.registry
    if expr.function_id and expr.function_id in registry.functions:
        return expr.function_id, registry.functions[expr.function_id]
    for function_id, function in registry.functions.items():
        if function.full_name == expr.function_name or function.name == expr.function_name:
            return function_id, function
    return None, None


def _bo_has_field(bo: Any, field_name: str) -> bool:
    return any(_field_name_from_identifier(field_id) == field_name or field_id == field_name for field_id in bo.field_ids)


def _bo_has_naming_sql(bo: Any, naming_sql: str) -> bool:
    return any(sql_id == naming_sql or _suffix_name(sql_id) == naming_sql for sql_id in bo.naming_sql_ids)


def _resolve_naming_sql(expr: QueryCallPlanNode, env: FilteredEnvironment) -> tuple[str, Any, str, list[dict[str, Any]]] | None:
    if expr.bo_id and expr.bo_id in env.registry.bos:
        bo = env.registry.bos[expr.bo_id]
        result = _resolve_naming_sql_for_bo(bo, expr)
        if result is not None:
            return expr.bo_id, bo, result[0], result[1]

    bo_id, bo = _resolve_bo(expr, env)
    if bo is not None and bo_id is not None:
        result = _resolve_naming_sql_for_bo(bo, expr)
        if result is not None:
            return bo_id, bo, result[0], result[1]

    for each_bo_id, each_bo in env.registry.bos.items():
        result = _resolve_naming_sql_for_bo(each_bo, expr)
        if result is not None:
            return each_bo_id, each_bo, result[0], result[1]
    return None


def _resolve_naming_sql_for_bo(bo: Any, expr: QueryCallPlanNode) -> tuple[str, list[dict[str, Any]]] | None:
    candidate_keys = [str(expr.naming_sql_id or "").strip(), str(expr.source_name or "").strip()]
    for key in candidate_keys:
        if not key:
            continue
        naming_sql_name = bo.naming_sql_name_by_key.get(key)
        if not naming_sql_name:
            continue
        param_defs = bo.naming_sql_param_meta_by_key.get(key) or bo.naming_sql_param_meta_by_key.get(naming_sql_name) or []
        if param_defs:
            return naming_sql_name, [dict(param) for param in param_defs]
        param_names = bo.naming_sql_param_names_by_key.get(key) or bo.naming_sql_param_names_by_key.get(naming_sql_name) or []
        return naming_sql_name, [{"param_name": name} for name in param_names]
    return None


def _extract_actual_param_type_from_expr(expr: ExprPlanNode) -> dict[str, Any] | None:
    if not isinstance(expr, LiteralPlanNode):
        return None
    if not isinstance(expr.value, dict):
        return None
    value = expr.value
    if not any(key in value for key in ("data_type", "data_type_name", "is_list")):
        return None
    return {
        "data_type": str(value.get("data_type") or "").strip(),
        "data_type_name": str(value.get("data_type_name") or "").strip(),
        "is_list": value.get("is_list") if isinstance(value.get("is_list"), bool) else None,
    }


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


def _function_name_from_identifier(value: str) -> str:
    return value.split("function:", 1)[1] if value.startswith("function:") else value


def _bo_name_from_identifier(value: str) -> str:
    return value.split("bo:", 1)[1] if value.startswith("bo:") else value


def _suffix_name(value: str) -> str:
    return value.split(":")[-1] if value else value


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


def parse_program_plan_payload(raw: dict[str, Any]) -> ProgramPlan:
    try:
        data = dict(raw)
        if isinstance(data.get("raw_plan"), str):
            try:
                data["raw_plan"] = json.loads(data["raw_plan"])
            except json.JSONDecodeError:
                data["raw_plan"] = {"raw": data["raw_plan"]}
        if "raw_plan" not in data:
            data["raw_plan"] = raw
        return ProgramPlan.model_validate(data)
    except ValidationError:
        return adapt_legacy_plan(raw)
