"""Default resource matcher service."""

from __future__ import annotations

from typing import Iterable, Set

from billing_dsl_agent.services.resource_index import (
    build_bo_index_from_list,
    build_context_index_from_vars,
    build_function_index,
)
from billing_dsl_agent.types.common import ContextScope, QueryMode
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent
from billing_dsl_agent.types.plan import (
    BOBinding,
    ContextBinding,
    FunctionBinding,
    MissingResource,
    ResolvedEnvironment,
    ResourceBinding,
)


class DefaultResourceMatcher:
    """Minimal but working matcher using string-based heuristic matching."""

    def match(self, intent: NodeIntent, env: ResolvedEnvironment) -> ResourceBinding:
        requirement = (intent.raw_requirement or "").strip()

        global_index = build_context_index_from_vars(env.global_context_vars)
        local_index = build_context_index_from_vars(env.local_context_vars)
        bo_index = build_bo_index_from_list(env.available_bos)
        function_index = build_function_index(env.available_functions)

        context_bindings: list[ContextBinding] = []
        bo_bindings: list[BOBinding] = []
        function_bindings: list[FunctionBinding] = []
        missing_resources: list[MissingResource] = []

        context_seen: Set[tuple[str, ContextScope, str | None]] = set()
        bo_seen: Set[tuple[str, QueryMode, str | None]] = set()
        function_seen: Set[tuple[str, str]] = set()

        wants_context = IntentSourceType.CONTEXT in intent.source_types
        wants_local = IntentSourceType.LOCAL_CONTEXT in intent.source_types
        wants_bo = IntentSourceType.BO_QUERY in intent.source_types or IntentSourceType.NAMING_SQL in intent.source_types
        wants_fn = IntentSourceType.FUNCTION in intent.source_types

        op_texts = [op.description for op in intent.operations]
        search_texts = [requirement, *op_texts]

        if wants_context or self._contains_any(search_texts, ["$ctx$", "context", "上下文"]):
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
                    MissingResource(
                        resource_type="context",
                        resource_name="global_context",
                        reason="No matched global context variable in requirement/operations.",
                    )
                )

        if wants_local or self._contains_any(search_texts, ["$local$", "local", "局部"]):
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

        if wants_bo or self._contains_any(search_texts, ["select", "fetch", "bo"]):
            matched_bo_names = self._match_names(search_texts, bo_index.by_name.keys())
            inferred_mode = self._infer_query_mode(search_texts)
            for bo_name in matched_bo_names:
                key = (bo_name, inferred_mode, None)
                if key not in bo_seen:
                    bo_seen.add(key)
                    bo_bindings.append(BOBinding(bo_name=bo_name, query_mode=inferred_mode))
            if wants_bo and not matched_bo_names:
                missing_resources.append(
                    MissingResource(
                        resource_type="bo",
                        resource_name="bo_query_target",
                        reason="No matched BO name in requirement/operations.",
                    )
                )

        if wants_fn or self._contains_any(search_texts, ["(", "函数", "function", "if", "exists"]):
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

        return ResourceBinding(
            context_bindings=context_bindings,
            bo_bindings=bo_bindings,
            function_bindings=function_bindings,
            missing_resources=missing_resources,
        )

    @staticmethod
    def _contains_any(texts: Iterable[str], probes: Iterable[str]) -> bool:
        lowers = [t.lower() for t in texts if t]
        return any(p.lower() in text for text in lowers for p in probes)

    @staticmethod
    def _match_names(texts: Iterable[str], names: Iterable[str]) -> list[str]:
        lowers = [t.lower() for t in texts if t]
        matched: list[str] = []
        for name in names:
            if not name:
                continue
            lname = name.lower()
            if any(lname in text for text in lowers):
                matched.append(name)
        return matched

    @staticmethod
    def _match_context_bindings(texts: Iterable[str], paths: Iterable[str]) -> list[str]:
        return DefaultResourceMatcher._match_names(texts, paths)

    @staticmethod
    def _field_name_from_path(path: str, var_name: str) -> str | None:
        if path == var_name:
            return None
        prefix = f"{var_name}."
        return path[len(prefix) :] if path.startswith(prefix) else None

    @staticmethod
    def _infer_query_mode(texts: Iterable[str]) -> QueryMode:
        joined = " ".join(t.lower() for t in texts if t)
        if "fetch_one" in joined:
            return QueryMode.FETCH_ONE
        if "fetch" in joined:
            return QueryMode.FETCH
        if "select_one" in joined:
            return QueryMode.SELECT_ONE
        return QueryMode.SELECT
