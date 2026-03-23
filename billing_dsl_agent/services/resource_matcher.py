"""Default resource matcher service."""

from __future__ import annotations

from typing import Iterable, Sequence

from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, QueryMode
from billing_dsl_agent.types.context import ContextVarDef
from billing_dsl_agent.types.function import FunctionDef
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.plan import (
    BOBinding,
    ContextBinding,
    FunctionBinding,
    MissingResource,
    ResolvedEnvironment,
    ResourceBinding,
)

_ZH_CUSTOMER_GENDER = "\u5ba2\u6237\u6027\u522b"
_ZH_CUSTOMER_NAME = "\u5ba2\u6237\u540d\u79f0"
_ZH_BILL_CYCLE = "\u8d26\u671f"


class DefaultResourceMatcher:
    """Bind semantic slots to concrete context, BO, field and function resources."""

    _FIELD_ALIASES: dict[str, tuple[str, ...]] = {
        _ZH_CUSTOMER_GENDER: ("gender", "sex", "customerGender", "custSex"),
        "gender": ("gender", "sex", "customerGender", "custSex"),
        "sex": ("sex", "gender", "custSex"),
        _ZH_CUSTOMER_NAME: ("name", "customerName", "custName"),
        "name": ("name", "customerName", "custName"),
        _ZH_BILL_CYCLE: ("billCycleId", "billCycle", "cycle", "iIrrBillCycle"),
        "prepareId": ("prepareId",),
        "billCycleId": ("billCycleId", "billCycle", "cycle"),
        "regionId": ("regionId", "regionCode"),
        "amount": ("amount", "amt", "money"),
    }

        context_bindings: list[ContextBinding] = []
        bo_bindings: list[BOBinding] = []
        function_bindings: list[FunctionBinding] = []
        missing_resources: list[MissingResource] = []
        semantic_bindings: dict[str, str] = {}

        context_seen: Set[tuple[str, ContextScope, str | None]] = set()
        bo_seen: Set[tuple[str, QueryMode, str | None]] = set()
        function_seen: Set[tuple[str, str]] = set()

        wants_context = IntentSourceType.CONTEXT in intent.source_types
        wants_local = IntentSourceType.LOCAL_CONTEXT in intent.source_types
        wants_bo = IntentSourceType.BO_QUERY in intent.source_types or IntentSourceType.NAMING_SQL in intent.source_types
        wants_fn = IntentSourceType.FUNCTION in intent.source_types

        op_texts = [op.description for op in intent.operations]
        search_texts = [requirement, *op_texts]
        context_keyword_hit = self._contains_any(search_texts, ["$ctx$", "context", "上下文"])
        local_keyword_hit = self._contains_any(search_texts, ["$local$", "local", "局部"])
        bo_keyword_hit = self._contains_any(search_texts, ["select", "fetch", "bo"])
        fn_keyword_hit = self._contains_any(search_texts, ["(", "函数", "function", "if", "exists"])

        if wants_context or context_keyword_hit:
            global_index = build_context_path_index(env.global_context_vars)
            matched = self._match_context_bindings(search_texts, global_index.by_path.keys())
            for name in matched:
                var = global_index.by_path[name]
                key = (var.name, ContextScope.GLOBAL, self._field_name_from_path(name, var.name))
                if key not in context_seen:
                    context_seen.add(key)
                    context_bindings.append(
                        ContextBinding(var_name=var.name, scope=ContextScope.GLOBAL, field_name=key[2])
                    )
            if wants_context and not matched:
                missing_resources.append(
                    self._build_missing_resource(
                        resource_type="context",
                        resource_name=hint,
                        reason=f"Unable to bind context hint: {hint}",
                    )
                )
                continue

        if wants_local or local_keyword_hit:
            local_index = build_context_path_index(env.local_context_vars)
            matched = self._match_context_bindings(search_texts, local_index.by_path.keys())
            for name in matched:
                var = local_index.by_path[name]
                key = (var.name, ContextScope.LOCAL, self._field_name_from_path(name, var.name))
                if key not in context_seen:
                    context_seen.add(key)
                    context_bindings.append(
                        ContextBinding(var_name=var.name, scope=ContextScope.LOCAL, field_name=key[2])
                    )
            if wants_local and not matched:
                missing_resources.append(
                    MissingResource(
                        resource_type="local_context",
                        resource_name="local_context",
                        reason="No matched local context variable in requirement/operations.",
                    )
                )
            )
            return

        if wants_bo or bo_keyword_hit:
            bo_index = build_bo_index(env.available_bos)
            matched_bo_names = self._match_names(search_texts, bo_index.by_name.keys())
            inferred_mode = self._infer_query_mode(search_texts)
            for bo_name in matched_bo_names:
                key = (bo_name, inferred_mode, None)
                if key not in bo_seen:
                    bo_seen.add(key)
                    bo_bindings.append(BOBinding(bo_name=bo_name, query_mode=inferred_mode))
            if wants_bo and not matched_bo_names:
                missing_resources.append(
                    self._build_missing_resource(
                        resource_type="bo_field",
                        resource_name=f"{bo.name}.{target_field}",
                        reason=f"Unable to bind target field `{target_field}` on BO `{bo.name}`.",
                    )
                )
            else:
                selected_field_names.append(matched_field)
                semantic_bindings["target_field"] = matched_field

        if wants_fn or fn_keyword_hit:
            function_index = build_function_index(env.available_functions)
            matched_full = self._match_names(search_texts, function_index.by_full_name.keys())
            for full_name in matched_full:
                fn = function_index.by_full_name[full_name]
                key = (fn.class_name, fn.method_name)
                if key not in function_seen:
                    function_seen.add(key)
                    function_bindings.append(FunctionBinding(class_name=fn.class_name, method_name=fn.method_name))

            matched_methods = self._match_names(search_texts, function_index.by_method_name.keys())
            for method_name in matched_methods:
                for fn in function_index.by_method_name.get(method_name, []):
                    key = (fn.class_name, fn.method_name)
                    if key not in function_seen:
                        function_seen.add(key)
                        function_bindings.append(FunctionBinding(class_name=fn.class_name, method_name=fn.method_name))

            if wants_fn and not (matched_full or matched_methods):
                missing_resources.append(
                    MissingResource(
                        resource_type="function",
                        resource_name="function_call_target",
                        reason="No matched function name in requirement/operations.",
                    )
                )
            )
            return

        function_bindings.append(FunctionBinding(class_name=fn.class_name, method_name=fn.method_name))
        semantic_bindings["function_name"] = fn.full_name

    def _match_context_hint(
        self,
        hint: str,
        env: ResolvedEnvironment,
        prefer_local: bool = False,
    ) -> ContextBinding | None:
        probes = self._build_context_probes(hint)
        scope_order = (
            ((ContextScope.LOCAL, env.local_context_vars), (ContextScope.GLOBAL, env.global_context_vars))
            if prefer_local
            else ((ContextScope.GLOBAL, env.global_context_vars), (ContextScope.LOCAL, env.local_context_vars))
        )

        for scope, vars_ in scope_order:
            binding = self._match_context_hint_in_scope(scope, vars_, probes)
            if binding is not None:
                return binding
        return None

    def _match_context_hint_in_scope(
        self,
        scope: ContextScope,
        context_vars: Sequence[ContextVarDef],
        probes: Sequence[str],
    ) -> ContextBinding | None:
        exact_var_match: ContextBinding | None = None
        partial_var_match: ContextBinding | None = None
        exact_field_match: ContextBinding | None = None
        partial_field_match: ContextBinding | None = None

        for var in context_vars or []:
            var_name = (var.name or "").strip()
            normalized_var = self._normalize_token(var_name)
            if normalized_var in probes:
                exact_var_match = exact_var_match or ContextBinding(var_name=var_name, scope=scope)
            elif any(probe and (probe in normalized_var or normalized_var in probe) for probe in probes):
                partial_var_match = partial_var_match or ContextBinding(var_name=var_name, scope=scope)

            for field in var.fields or []:
                field_name = (field.name or "").strip()
                normalized_field = self._normalize_token(field_name)
                path_tail = self._normalize_token(f"{var_name}.{field_name}")
                if normalized_field in probes or path_tail in probes:
                    exact_field_match = exact_field_match or ContextBinding(
                        var_name=var_name,
                        scope=scope,
                        field_name=field_name,
                    )
                elif any(
                    probe
                    and (
                        probe in normalized_field
                        or normalized_field in probe
                        or probe in path_tail
                        or path_tail in probe
                    )
                    for probe in probes
                ):
                    partial_field_match = partial_field_match or ContextBinding(
                        var_name=var_name,
                        scope=scope,
                        field_name=field_name,
                    )

        return exact_field_match or exact_var_match or partial_field_match or partial_var_match

    def _match_bo_name(self, bo_name: str, available_bos: Sequence[BODef]) -> BODef | None:
        normalized_name = self._normalize_token(bo_name)
        if not normalized_name:
            return None

        exact_match = next(
            (bo for bo in available_bos if self._normalize_token(bo.name) == normalized_name),
            None,
        )
        if exact_match is not None:
            return exact_match

        return next(
            (
                bo
                for bo in available_bos
                if normalized_name in self._normalize_token(bo.name) or self._normalize_token(bo.name) in normalized_name
            ),
            None,
        )

    def _match_bo_field(self, bo: BODef, target_field: str) -> str | None:
        probes = self._build_context_probes(target_field)

        for field in bo.fields or []:
            field_name = (field.name or "").strip()
            normalized_field = self._normalize_token(field_name)
            if normalized_field in probes:
                return field_name

        for field in bo.fields or []:
            field_name = (field.name or "").strip()
            normalized_field = self._normalize_token(field_name)
            if any(probe and (probe in normalized_field or normalized_field in probe) for probe in probes):
                return field_name

        return None

    def _match_function(self, function_name: str, available_functions: Sequence[FunctionDef]) -> FunctionDef | None:
        normalized_full_name = self._normalize_token(function_name)
        if not normalized_full_name:
            return None

        exact_full_name = next(
            (fn for fn in available_functions if self._normalize_token(fn.full_name) == normalized_full_name),
            None,
        )
        if exact_full_name is not None:
            return exact_full_name

        method_name = function_name.split(".")[-1]
        normalized_method = self._normalize_token(method_name)
        exact_method = next(
            (fn for fn in available_functions if self._normalize_token(fn.method_name) == normalized_method),
            None,
        )
        if exact_method is not None:
            return exact_method

        return next(
            (
                fn
                for fn in available_functions
                if normalized_method in self._normalize_token(fn.method_name)
                or normalized_full_name in self._normalize_token(fn.full_name)
            ),
            None,
        )

    def _infer_query_mode(self, semantic_slots: dict[str, object]) -> QueryMode:
        raw_mode = str(semantic_slots.get("query_mode") or "").strip().lower()
        if raw_mode == "select_one":
            return QueryMode.SELECT_ONE
        if raw_mode == "select":
            return QueryMode.SELECT
        if raw_mode == "fetch_one":
            return QueryMode.FETCH_ONE
        if raw_mode == "fetch":
            return QueryMode.FETCH
        return QueryMode.SELECT

    def _build_context_probes(self, hint: str) -> list[str]:
        normalized_hint = self._normalize_token(hint)
        probes = [normalized_hint]
        for alias in self._FIELD_ALIASES.get(hint, ()):
            probes.append(self._normalize_token(alias))
        for alias in self._FIELD_ALIASES.get(normalized_hint, ()):
            probes.append(self._normalize_token(alias))
        return self._dedup_strings([probe for probe in probes if probe])

    @staticmethod
    def _binding_to_path(binding: ContextBinding) -> str:
        prefix = "$ctx$" if binding.scope == ContextScope.GLOBAL else "$local$"
        path = f"{prefix}.{binding.var_name}"
        if binding.field_name:
            path = f"{path}.{binding.field_name}"
        return path

    @staticmethod
    def _build_missing_resource(resource_type: str, resource_name: str, reason: str) -> MissingResource:
        return MissingResource(resource_type=resource_type, resource_name=resource_name, reason=reason)

    @staticmethod
    def _dedup_context_bindings(bindings: Sequence[ContextBinding]) -> list[ContextBinding]:
        deduped: list[ContextBinding] = []
        seen: set[tuple[str, str, str | None]] = set()
        for binding in bindings:
            key = (binding.var_name, binding.scope.value, binding.field_name)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(binding)
        return deduped

    @staticmethod
    def _dedup_bo_bindings(bindings: Sequence[BOBinding]) -> list[BOBinding]:
        deduped: list[BOBinding] = []
        seen: set[tuple[str, str, tuple[str, ...]]] = set()
        for binding in bindings:
            key = (binding.bo_name, binding.query_mode.value, tuple(binding.selected_field_names))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(binding)
        return deduped

    @staticmethod
    def _dedup_function_bindings(bindings: Sequence[FunctionBinding]) -> list[FunctionBinding]:
        deduped: list[FunctionBinding] = []
        seen: set[tuple[str, str]] = set()
        for binding in bindings:
            key = (binding.class_name, binding.method_name)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(binding)
        return deduped

    @staticmethod
    def _dedup_missing_resources(resources: Sequence[MissingResource]) -> list[MissingResource]:
        deduped: list[MissingResource] = []
        seen: set[tuple[str, str, str]] = set()
        for resource in resources:
            key = (resource.resource_type, resource.resource_name, resource.reason)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(resource)
        return deduped

    @staticmethod
    def _normalize_token(value: str) -> str:
        return "".join(ch for ch in (value or "").strip().lower() if ch.isalnum())

    @staticmethod
    def _dedup_strings(values: Sequence[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = (value or "").strip()
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped
