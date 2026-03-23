from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from billing_dsl_agent.models import FilteredEnvironment, NodeDef, ResourceRegistry
from billing_dsl_agent.semantic_selector import CandidateSummary, MockSemanticSelector, SemanticSelector


@dataclass(slots=True)
class EnvironmentBuilder:
    semantic_selector: SemanticSelector = field(default_factory=MockSemanticSelector)

    def build_filtered_environment(self, node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> FilteredEnvironment:
        local_context_ids = self._select_local_context_ids(node_info, registry)
        global_context_ids = self._select_global_context_ids(node_info, user_query, registry)
        bo_ids = self._select_bo_ids(node_info, user_query, registry)
        function_ids = self._select_function_ids(node_info, user_query, registry)
        return FilteredEnvironment(
            registry=registry,
            selected_global_context_ids=global_context_ids,
            selected_local_context_ids=local_context_ids,
            selected_bo_ids=bo_ids,
            selected_function_ids=function_ids,
        )

    def _select_local_context_ids(self, node_info: NodeDef, registry: ResourceRegistry) -> List[str]:
        parent_segments = [seg for seg in node_info.node_path.split(".")[:-1] if seg]
        matched: List[str] = []
        for context in registry.contexts.values():
            if context.scope != "local":
                continue
            context_segments = context.path.split(".")
            if any(seg in context_segments for seg in parent_segments):
                matched.append(context.resource_id)
        if not matched:
            matched = [ctx.resource_id for ctx in registry.contexts.values() if ctx.scope == "local"]
        return sorted(set(matched))

    def _select_global_context_ids(self, node_info: NodeDef, user_query: str, registry: ResourceRegistry) -> List[str]:
        domains = self._recall_domains(node_info, user_query, {c.domain for c in registry.contexts.values() if c.scope == "global"})
        candidates = [
            CandidateSummary(resource_id=c.resource_id, description=f"{c.name} {c.description} {c.path}", tags=[c.domain, *c.tags])
            for c in registry.contexts.values()
            if c.scope == "global" and c.domain in domains
        ]
        return self.semantic_selector.select("context", node_info, user_query, candidates)

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
