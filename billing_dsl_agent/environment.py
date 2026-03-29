from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from billing_dsl_agent.context_selector import ContextSelector
from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    EnvironmentSelectionBundle,
    FilteredEnvironment,
    FunctionResource,
    NodeDef,
    ResourceRegistry,
    ResourceSelectionDebug,
)
from billing_dsl_agent.resource_manager import ResourceManager
from billing_dsl_agent.semantic_selector import CandidateSummary, MockSemanticSelector, SemanticSelector, SelectionResult


@dataclass(slots=True)
class EnvironmentBuilder:
    semantic_selector: SemanticSelector = field(default_factory=MockSemanticSelector)
    resource_manager: ResourceManager = field(default_factory=ResourceManager)

    def build_filtered_environment(self, node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> FilteredEnvironment:
        working_registry = ResourceRegistry(
            contexts=dict(registry.contexts),
            bos=dict(registry.bos),
            functions=dict(registry.functions),
            edsl_tree=dict(registry.edsl_tree),
        )

        context_selector = ContextSelector(semantic_selector=self.semantic_selector)
        local_contexts = context_selector.resolve_local_context_from_edsl_tree(node_info.node_path, working_registry.edsl_tree)
        working_registry.contexts.update(local_contexts)

        local_context_ids = sorted(local_contexts.keys())
        selected_local_contexts = [working_registry.contexts[item] for item in local_context_ids if item in working_registry.contexts]
        local_debug = ResourceSelectionDebug(
            resource_type="local_context",
            strategy="rule_only",
            candidate_ids=local_context_ids,
            selected_ids=local_context_ids,
            fallback_used=False,
            llm_errors=[],
        )

        eligible_global_contexts = self._eligible_global_contexts(node_info, user_query, working_registry)
        eligible_bos = self._eligible_bos(node_info, user_query, working_registry)
        eligible_functions = dict(working_registry.functions)

        indexes = self.resource_manager.build_indexes(
            context_registry_or_vars=list(eligible_global_contexts.values()),
            bo_registry_or_list=list(eligible_bos.values()),
            function_registry_or_list=list(eligible_functions.values()),
        )
        candidate_set = self.resource_manager.select_candidates(
            user_query=user_query,
            node_def=node_info,
            indexes=indexes,
        )

        global_context_selection = self._select_global_contexts(
            node_info=node_info,
            user_query=user_query,
            eligible_contexts=eligible_global_contexts,
            candidate_set=candidate_set,
        )
        global_context_selection.selected_ids = self._augment_global_context_ids(
            global_context_selection.selected_ids,
            eligible_global_contexts,
        )
        bo_selection = self._select_bos(
            node_info=node_info,
            user_query=user_query,
            eligible_bos=eligible_bos,
            candidate_set=candidate_set,
        )
        function_selection = self._select_functions(
            node_info=node_info,
            user_query=user_query,
            functions=eligible_functions,
            candidate_set=candidate_set,
        )

        selected_global_contexts = self._resolve_contexts(global_context_selection.selected_ids, eligible_global_contexts)
        selected_bos = self._resolve_bos(bo_selection.selected_ids, eligible_bos)
        selected_functions = self._resolve_functions(function_selection.selected_ids, eligible_functions)

        selection_debug = EnvironmentSelectionBundle(
            global_context=self._build_selection_debug("global_context", global_context_selection),
            local_context=local_debug,
            bo=self._build_selection_debug("bo", bo_selection),
            function=self._build_selection_debug("function", function_selection),
        )

        return FilteredEnvironment(
            registry=working_registry,
            selected_global_context_ids=[item.resource_id for item in selected_global_contexts],
            selected_local_context_ids=local_context_ids,
            selected_bo_ids=[item.resource_id for item in selected_bos],
            selected_function_ids=[item.resource_id for item in selected_functions],
            selected_global_contexts=selected_global_contexts,
            selected_local_contexts=selected_local_contexts,
            selected_bos=selected_bos,
            selected_functions=selected_functions,
            selection_debug=selection_debug,
        )

    def _select_global_contexts(
        self,
        node_info: NodeDef,
        user_query: str,
        eligible_contexts: Dict[str, ContextResource],
        candidate_set: Any,
    ) -> SelectionResult:
        path_to_context = {item.path: item for item in eligible_contexts.values()}
        candidates = [
            CandidateSummary(
                resource_id=resource.resource_id,
                description=f"{resource.name} {resource.description} {resource.path}",
                tags=[resource.domain, *resource.tags],
            )
            for item in candidate_set.context_candidates
            if (resource := path_to_context.get(item.path)) is not None
        ]
        if not candidates:
            candidates = [
                CandidateSummary(
                    resource_id=resource.resource_id,
                    description=f"{resource.name} {resource.description} {resource.path}",
                    tags=[resource.domain, *resource.tags],
                )
                for resource in eligible_contexts.values()
            ]
        return self.semantic_selector.select_with_debug("context", node_info, user_query, candidates)

    def _select_bos(
        self,
        node_info: NodeDef,
        user_query: str,
        eligible_bos: Dict[str, BOResource],
        candidate_set: Any,
    ) -> SelectionResult:
        bo_name_to_resource = {item.bo_name: item for item in eligible_bos.values()}
        candidates = [
            CandidateSummary(
                resource_id=resource.resource_id,
                description=f"{resource.bo_name} {resource.description} fields={' '.join(resource.field_ids)} datasource={resource.data_source}",
                tags=[resource.scope, resource.data_source, *resource.tags],
            )
            for item in candidate_set.bo_candidates
            if (resource := bo_name_to_resource.get(item.bo_name)) is not None
        ]
        if not candidates:
            candidates = [
                CandidateSummary(
                    resource_id=resource.resource_id,
                    description=f"{resource.bo_name} {resource.description} fields={' '.join(resource.field_ids)} datasource={resource.data_source}",
                    tags=[resource.scope, resource.data_source, *resource.tags],
                )
                for resource in eligible_bos.values()
            ]
        return self.semantic_selector.select_with_debug("bo", node_info, user_query, candidates)

    def _select_functions(
        self,
        node_info: NodeDef,
        user_query: str,
        functions: Dict[str, FunctionResource],
        candidate_set: Any,
    ) -> SelectionResult:
        function_by_full_name = {item.full_name: item for item in functions.values()}
        function_by_function_id = {item.function_id: item for item in functions.values()}
        candidates = []
        for item in candidate_set.function_candidates:
            resource = function_by_full_name.get(item.full_name) or function_by_function_id.get(item.function_id)
            if resource is None:
                continue
            candidates.append(
                CandidateSummary(
                    resource_id=resource.resource_id,
                    description=f"{resource.function_id} {resource.full_name} {resource.description} {resource.signature_display} return={resource.return_type}",
                    tags=[resource.scope, *resource.params, *resource.tags],
                )
            )
        if not candidates:
            candidates = [
                CandidateSummary(
                    resource_id=resource.resource_id,
                    description=f"{resource.function_id} {resource.full_name} {resource.description} {resource.signature_display} return={resource.return_type}",
                    tags=[resource.scope, *resource.params, *resource.tags],
                )
                for resource in functions.values()
            ]
        return self.semantic_selector.select_with_debug("function", node_info, user_query, candidates)

    def _eligible_global_contexts(
        self,
        node_info: NodeDef,
        user_query: str,
        registry: ResourceRegistry,
    ) -> Dict[str, ContextResource]:
        global_contexts = {key: value for key, value in registry.contexts.items() if value.scope == "global"}
        domains = self._recall_domains(node_info, user_query, {c.domain for c in global_contexts.values()})
        return {key: value for key, value in global_contexts.items() if value.domain in domains}

    def _eligible_bos(
        self,
        node_info: NodeDef,
        user_query: str,
        registry: ResourceRegistry,
    ) -> Dict[str, BOResource]:
        bos = dict(registry.bos)
        if node_info.is_ab and node_info.ab_data_sources:
            allowed = set(node_info.ab_data_sources)
            return {key: value for key, value in bos.items() if value.data_source in allowed}

        if node_info.is_ab:
            return bos

        domains = self._recall_domains(node_info, user_query, {bo.domain for bo in bos.values()})
        return {key: value for key, value in bos.items() if value.domain in domains}

    def _resolve_contexts(
        self,
        selected_ids: List[str],
        contexts: Dict[str, ContextResource],
    ) -> List[ContextResource]:
        return [contexts[item] for item in selected_ids if item in contexts]

    def _resolve_bos(self, selected_ids: List[str], bos: Dict[str, BOResource]) -> List[BOResource]:
        return [bos[item] for item in selected_ids if item in bos]

    def _resolve_functions(
        self,
        selected_ids: List[str],
        functions: Dict[str, FunctionResource],
    ) -> List[FunctionResource]:
        return [functions[item] for item in selected_ids if item in functions]

    def _build_selection_debug(self, resource_type: str, selection: SelectionResult) -> ResourceSelectionDebug:
        return ResourceSelectionDebug(
            resource_type=resource_type,
            strategy="rule_recall_plus_llm",
            candidate_ids=list(selection.candidate_ids),
            selected_ids=list(selection.selected_ids),
            fallback_used=selection.fallback_used,
            llm_errors=list(selection.llm_errors),
        )

    def _recall_domains(self, node_info: NodeDef, user_query: str, domains: set[str]) -> set[str]:
        text = f"{node_info.node_name} {node_info.node_path} {node_info.description} {user_query}".lower()
        selected = {domain for domain in domains if domain.lower() in text}
        return selected or set(domains)

    def _augment_global_context_ids(
        self,
        selected_ids: List[str],
        contexts: Dict[str, ContextResource],
    ) -> List[str]:
        ordered_ids = []
        seen: set[str] = set()
        for item in selected_ids:
            if item in contexts and item not in seen:
                seen.add(item)
                ordered_ids.append(item)

        path_to_id = {item.path: item.resource_id for item in contexts.values()}
        for item in ordered_ids.copy():
            context = contexts.get(item)
            if context is None or "." not in context.path:
                continue
            parent_path = context.path.rsplit(".", 1)[0]
            sibling_id = path_to_id.get(f"{parent_path}.id")
            if sibling_id and sibling_id not in seen:
                seen.add(sibling_id)
                ordered_ids.append(sibling_id)
        return ordered_ids


def build_filtered_environment(node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> FilteredEnvironment:
    return EnvironmentBuilder().build_filtered_environment(node_info, user_query, registry)
