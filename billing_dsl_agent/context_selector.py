from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

from billing_dsl_agent.models import ContextResource, NodeDef, ResourceRegistry
from billing_dsl_agent.semantic_selector import CandidateSummary, SemanticSelector


@dataclass(slots=True)
class ContextSelector:
    semantic_selector: SemanticSelector

    def resolve_local_context_from_edsl_tree(self, node_path: str, edsl_tree: Dict[str, Any]) -> Dict[str, ContextResource]:
        node_result = self._find_node_with_ancestors(edsl_tree, node_path)
        if node_result is None:
            return {}

        _, ancestors = node_result
        resources: Dict[str, ContextResource] = {}
        for ancestor in ancestors:
            node_type = str(ancestor.get("node_type") or ancestor.get("type") or "").strip().lower()
            if node_type not in {"parent", "parent list"}:
                continue
            local_context = ancestor.get("local_context")
            for item in self._iter_local_context(local_context):
                resource = self._normalize_local_context_item(item, ancestor)
                resources[resource.resource_id] = resource
        return resources

    def select_global_context_from_context_json(
        self,
        user_query: str,
        node_info: NodeDef,
        registry: ResourceRegistry,
    ) -> List[str]:
        domains = self._recall_domains(node_info, user_query, {c.domain for c in registry.contexts.values() if c.scope == "global"})
        candidates = [
            CandidateSummary(resource_id=c.resource_id, description=f"{c.name} {c.description} {c.path}", tags=[c.domain, *c.tags])
            for c in registry.contexts.values()
            if c.scope == "global" and c.domain in domains
        ]
        return self.semantic_selector.select("context", node_info, user_query, candidates)

    def _find_node_with_ancestors(
        self, tree: Dict[str, Any], node_path: str
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]] | None:
        if not isinstance(tree, dict):
            return None

        roots = tree.get("nodes") if isinstance(tree.get("nodes"), list) else [tree]
        for root in roots:
            found = self._dfs_find(root, node_path=node_path, parent_path="", ancestors=[])
            if found is not None:
                return found
        return None

    def _dfs_find(
        self,
        node: Dict[str, Any],
        node_path: str,
        parent_path: str,
        ancestors: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]] | None:
        if not isinstance(node, dict):
            return None

        current_path = self._node_path(node, parent_path)
        if current_path == node_path:
            return node, ancestors

        for child in self._children(node):
            found = self._dfs_find(child, node_path=node_path, parent_path=current_path, ancestors=[*ancestors, node])
            if found is not None:
                return found
        return None

    def _node_path(self, node: Dict[str, Any], parent_path: str) -> str:
        explicit = str(node.get("node_path") or node.get("path") or "").strip()
        if explicit:
            return explicit
        segment = str(node.get("node_name") or node.get("name") or node.get("key") or "").strip()
        if not segment:
            return parent_path
        return f"{parent_path}.{segment}" if parent_path else segment

    def _children(self, node: Dict[str, Any]) -> Sequence[Dict[str, Any]]:
        for key in ("children", "nodes", "sub_nodes"):
            value = node.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _iter_local_context(self, local_context: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(local_context, dict):
            for key, value in local_context.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault("name", key)
                    yield row
                else:
                    yield {"name": key, "description": str(value)}
        elif isinstance(local_context, list):
            for item in local_context:
                if isinstance(item, dict):
                    yield item

    def _normalize_local_context_item(self, item: Dict[str, Any], ancestor: Dict[str, Any]) -> ContextResource:
        explicit_id = str(item.get("resource_id") or item.get("id") or "").strip()
        name = str(item.get("name") or item.get("context_name") or item.get("key") or "").strip()
        description = str(item.get("description") or item.get("desc") or "").strip()
        raw_path = str(item.get("path") or item.get("context_path") or "").strip()
        ancestor_path = str(ancestor.get("node_path") or ancestor.get("path") or ancestor.get("node_name") or "")
        stable_key = explicit_id or f"{ancestor_path}:{name}:{raw_path}:{description}"
        digest = hashlib.md5(stable_key.encode("utf-8")).hexdigest()[:12]
        resource_id = explicit_id or f"context:local:{digest}"
        context_path = raw_path or f"$local$.{name or digest}"
        return ContextResource(
            resource_id=resource_id,
            name=name or digest,
            path=context_path,
            scope="local",
            domain="local",
            description=description,
            tags=["edsl_local_context", str(ancestor.get("node_type") or ancestor.get("type") or "")],
        )

    def _recall_domains(self, node_info: NodeDef, user_query: str, domains: set[str]) -> set[str]:
        text = f"{node_info.node_name} {node_info.node_path} {node_info.description} {user_query}".lower()
        selected = {domain for domain in domains if domain.lower() in text}
        return selected or set(domains)
