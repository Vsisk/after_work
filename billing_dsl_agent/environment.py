from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from billing_dsl_agent.context_selector import ContextSelector
from billing_dsl_agent.models import FilteredEnvironment, NodeDef, ResourceRegistry
from billing_dsl_agent.semantic_selector import CandidateSummary, MockSemanticSelector, SemanticSelector


@dataclass(slots=True)
class EnvironmentBuilder:
    semantic_selector: SemanticSelector = field(default_factory=MockSemanticSelector)

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
        global_context_ids = context_selector.select_global_context_from_context_json(user_query, node_info, working_registry)
        bo_ids = self._select_bo_ids(node_info, user_query, working_registry)
        function_ids = self._select_function_ids(node_info, user_query, working_registry)
        return FilteredEnvironment(
            registry=working_registry,
            selected_global_context_ids=global_context_ids,
            selected_local_context_ids=local_context_ids,
            selected_bo_ids=bo_ids,
            selected_function_ids=function_ids,
        )

    def _select_bo_ids(self, node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> List[str]:
        bo_values = list(registry.bos.values())
        if node_info.is_ab and node_info.ab_data_sources:
            allowed = set(node_info.ab_data_sources)
            bo_values = [item for item in bo_values if item.data_source in allowed]

        if not node_info.is_ab:
            bo_domains = self._recall_domains(node_info, user_query, {bo.domain for bo in bo_values})
            bo_values = [item for item in bo_values if item.domain in bo_domains]

        candidates = [
            CandidateSummary(
                resource_id=bo.resource_id,
                description=f"{bo.bo_name} {bo.description} fields={' '.join(bo.field_ids)} datasource={bo.data_source}",
                tags=[bo.scope, bo.data_source, *bo.tags],
            )
            for bo in bo_values
        ]
        return self.semantic_selector.select("bo", node_info, user_query, candidates)

    def _select_function_ids(self, node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> List[str]:
        candidates = [
            CandidateSummary(
                resource_id=fn.resource_id,
                description=f"{fn.function_id} {fn.full_name} {fn.description} {fn.signature} return={fn.return_type}",
                tags=[fn.scope, *fn.params, *fn.tags],
            )
            for fn in registry.functions.values()
        ]
        return self.semantic_selector.select("function", node_info, user_query, candidates)

    def _recall_domains(self, node_info: NodeDef, user_query: str, domains: set[str]) -> set[str]:
        text = f"{node_info.node_name} {node_info.node_path} {node_info.description} {user_query}".lower()
        selected = {domain for domain in domains if domain.lower() in text}
        return selected or set(domains)


def build_filtered_environment(node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> FilteredEnvironment:
    return EnvironmentBuilder().build_filtered_environment(node_info, user_query, registry)
