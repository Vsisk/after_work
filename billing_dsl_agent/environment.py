from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from billing_dsl_agent.log_utils import get_logger
from billing_dsl_agent.local_context_normalizer import normalize_local_contexts
from billing_dsl_agent.local_context_resolver import resolve_visible_local_contexts
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
from billing_dsl_agent.semantic_selector import CandidateSummary, MockSemanticSelector, SemanticSelector, SelectionResult

logger = get_logger(__name__)


@dataclass(slots=True)
class EnvironmentBuilder:
    semantic_selector: SemanticSelector = field(default_factory=MockSemanticSelector)
    resource_manager: Any = None
    max_candidates_per_type: int = 20

    def build_filtered_environment(self, node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> FilteredEnvironment:
        logger.info(
            "environment_build_started node_id=%s node_path=%s user_query=%s",
            node_info.node_id,
            node_info.node_path,
            user_query,
        )
        working_registry = registry

        resolved_local_contexts = resolve_visible_local_contexts(working_registry.edsl_tree, node_info.node_path)
        visible_local_context = normalize_local_contexts(resolved_local_contexts)
        local_context_ids = [item.resource_id for item in visible_local_context.ordered_nodes]
        logger.info(
            "local_context_resolution_completed node_path=%s visible_local_context_ids=%s",
            node_info.node_path,
            local_context_ids,
        )
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
        eligible_functions = working_registry.functions
        logger.info(
            "environment_eligibility_completed eligible_global_contexts=%s eligible_bos=%s eligible_functions=%s",
            len(eligible_global_contexts),
            len(eligible_bos),
            len(eligible_functions),
        )

        global_context_selection = self._select_global_contexts(
            node_info=node_info,
            user_query=user_query,
            eligible_contexts=eligible_global_contexts,
        )
        global_context_selection.selected_ids = self._augment_global_context_ids(
            global_context_selection.selected_ids,
            eligible_global_contexts,
        )
        bo_selection = self._select_bos(
            node_info=node_info,
            user_query=user_query,
            eligible_bos=eligible_bos,
        )
        function_selection = self._select_functions(
            node_info=node_info,
            user_query=user_query,
            functions=eligible_functions,
        )

        selected_global_contexts = self._resolve_contexts(global_context_selection.selected_ids, eligible_global_contexts)
        selected_bos = self._resolve_bos(bo_selection.selected_ids, eligible_bos)
        selected_functions = self._resolve_functions(function_selection.selected_ids, eligible_functions)
        logger.info(
            "environment_selection_completed global_context_ids=%s bo_ids=%s function_ids=%s",
            [item.resource_id for item in selected_global_contexts],
            [item.resource_id for item in selected_bos],
            [item.resource_id for item in selected_functions],
        )

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
            visible_local_context=visible_local_context,
            selected_bos=selected_bos,
            selected_functions=selected_functions,
            selection_debug=selection_debug,
        )

    def _select_global_contexts(
        self,
        node_info: NodeDef,
        user_query: str,
        eligible_contexts: Dict[str, ContextResource],
    ) -> SelectionResult:
        candidates = [
            CandidateSummary(
                resource_id=resource.resource_id,
                description=self._short_text(resource.name, resource.description, resource.path),
                tags=[resource.domain, *resource.tags],
            )
            for resource in list(eligible_contexts.values())[: self.max_candidates_per_type]
        ]
        selection = self.semantic_selector.select_with_debug("context", node_info, user_query, candidates)
        selection.debug_info = {"resource_type": "context"}
        return selection

    def _select_bos(
        self,
        node_info: NodeDef,
        user_query: str,
        eligible_bos: Dict[str, BOResource],
    ) -> SelectionResult:
        candidates = [
            CandidateSummary(
                resource_id=resource.resource_id,
                description=self._short_text(
                    resource.bo_name,
                    resource.description,
                    "datasource=" + getattr(resource, "data_source", resource.scope),
                ),
                tags=[resource.scope, getattr(resource, "data_source", resource.scope), *resource.tags],
            )
            for resource in list(eligible_bos.values())[: self.max_candidates_per_type]
        ]
        selection = self.semantic_selector.select_with_debug("bo", node_info, user_query, candidates)
        selection.debug_info = {"resource_type": "bo"}
        return selection

    def _select_functions(
        self,
        node_info: NodeDef,
        user_query: str,
        functions: Dict[str, FunctionResource],
    ) -> SelectionResult:
        candidates = [
            self._function_candidate_summary(resource)
            for resource in list(functions.values())[: self.max_candidates_per_type]
        ]
        selection = self.semantic_selector.select_with_debug("function", node_info, user_query, candidates)
        selection.debug_info = {"resource_type": "function"}
        return selection

    def _eligible_global_contexts(
        self,
        node_info: NodeDef,
        user_query: str,
        registry: ResourceRegistry,
    ) -> Dict[str, ContextResource]:
        global_contexts = {key: value for key, value in registry.contexts.items() if value.scope == "global"}
        domains = self._recall_domains(node_info, user_query, {c.domain for c in global_contexts.values()})
        filtered = {key: value for key, value in global_contexts.items() if value.domain in domains}
        return filtered or global_contexts

    def _eligible_bos(
        self,
        node_info: NodeDef,
        user_query: str,
        registry: ResourceRegistry,
    ) -> Dict[str, BOResource]:
        bos = registry.bos
        if node_info.is_ab and node_info.ab_data_sources:
            allowed = set(node_info.ab_data_sources)
            return {
                key: value
                for key, value in bos.items()
                if getattr(value, "data_source", value.scope) in allowed
            }

        if node_info.is_ab:
            return bos

        domains = self._recall_domains(node_info, user_query, {bo.domain for bo in bos.values()})
        filtered = {key: value for key, value in bos.items() if value.domain in domains}
        return filtered or bos

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

    def _build_selection_debug(
        self,
        resource_type: str,
        selection: SelectionResult,
    ) -> ResourceSelectionDebug:
        return ResourceSelectionDebug(
            resource_type=resource_type,
            strategy="id_summary_plus_selector",
            candidate_ids=list(selection.candidate_ids),
            selected_ids=list(selection.selected_ids),
            fallback_used=selection.fallback_used,
            llm_errors=list(selection.llm_errors),
            retrieval_debug=dict(selection.debug_info),
        )

    def _recall_domains(self, node_info: NodeDef, user_query: str, domains: set[str]) -> set[str]:
        text = f"{node_info.node_name} {node_info.node_path} {node_info.description} {user_query}".lower()
        selected = {domain for domain in domains if domain.lower() in text}
        return selected or set(domains)

    def _function_candidate_summary(self, resource: FunctionResource) -> CandidateSummary:
        function_id = getattr(resource, "function_id", resource.resource_id)
        full_name = getattr(resource, "full_name", getattr(resource, "function_name", resource.name))
        description = getattr(resource, "description", getattr(resource, "function_name_zh", resource.name))
        signature_display = getattr(resource, "signature_display", "")
        return CandidateSummary(
            resource_id=resource.resource_id,
            description=self._short_text(
                function_id,
                full_name,
                description,
                signature_display,
                f"return={resource.return_type}",
            ),
            tags=[resource.scope, *resource.params, *resource.tags],
        )

    def _short_text(self, *parts: str, limit: int = 220) -> str:
        text = " ".join(part.strip() for part in parts if part and part.strip())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

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
