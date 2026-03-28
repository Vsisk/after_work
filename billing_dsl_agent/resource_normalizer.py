from __future__ import annotations

from dataclasses import dataclass
from typing import List

from billing_dsl_agent.bo_models import BODef
from billing_dsl_agent.context_models import ContextPropertyDef, NormalizedContextNode
from billing_dsl_agent.models import BOResource, ContextResource, FunctionResource, ResourceRegistry
from billing_dsl_agent.resource_loader import LoadedResources


@dataclass(slots=True)
class ResourceNormalizer:
    def normalize(self, loaded: LoadedResources) -> ResourceRegistry:
        contexts = self._normalize_global_contexts(loaded)
        bos = self._normalize_bos(loaded)
        functions = self._normalize_functions(loaded)
        return ResourceRegistry(contexts=contexts, bos=bos, functions=functions, edsl_tree=dict(loaded.edsl_tree or {}))

    def _normalize_global_contexts(self, loaded: LoadedResources) -> dict[str, ContextResource]:
        registry: dict[str, ContextResource] = {}
        normalized_nodes = loaded.context_registry.nodes_by_id
        if normalized_nodes:
            self._build_context_resources_from_normalized_nodes(normalized_nodes, registry)
            return registry

        root = loaded.context_registry.global_root
        if root is None:
            return registry

        def walk(node: ContextPropertyDef, parent_path: str) -> None:
            for index, child in enumerate(node.children):
                segment = child.name or child.id or f"node{index}"
                path = f"{parent_path}.{segment}" if parent_path else segment
                resource_id = f"context:{path}"
                domain = path.split(".")[1] if "." in path else "default"
                registry[resource_id] = ContextResource(
                    resource_id=resource_id,
                    name=child.name,
                    path=path,
                    scope="global",
                    domain=domain,
                    description=child.description,
                    tags=["context_json", child.metadata.get("raw_value_source_type", "")],
                )
                walk(child, path)

        walk(root, "$ctx$")
        return registry

    def _build_context_resources_from_normalized_nodes(
        self,
        normalized_nodes: dict[str, NormalizedContextNode],
        registry: dict[str, ContextResource],
    ) -> None:
        for node in sorted(normalized_nodes.values(), key=lambda item: (item.depth, item.access_path)):
            path = node.access_path
            if not path:
                continue
            resource_id = f"context:{path}"
            domain = path.split(".")[1] if "." in path else "default"
            registry[resource_id] = ContextResource(
                resource_id=resource_id,
                name=node.property_name,
                path=path,
                scope="global",
                domain=domain,
                description=node.annotation,
                tags=["context_json", node.context_kind, node.source_type],
            )

    def _normalize_bos(self, loaded: LoadedResources) -> dict[str, BOResource]:
        registry: dict[str, BOResource] = {}

        def add_items(items: List[BODef], scope: str) -> None:
            for bo in items:
                resource_id = f"bo:{bo.bo_name}"
                field_ids = [f"{resource_id}:field:{field.name}" for field in bo.fields]
                naming_sql_ids = [f"{resource_id}:sql:{sql.name}" for sql in bo.query_capability.naming_sqls if sql.name]
                naming_sql_name_by_key: dict[str, str] = {}
                naming_sql_param_names_by_key: dict[str, list[str]] = {}
                data_source = ""
                for sql in bo.query_capability.naming_sqls:
                    ds = str(sql.metadata.get("or_mapping_data_source") or "")
                    if ds:
                        data_source = ds
                    sql_name = str(sql.name or "").strip()
                    sql_id = str(sql.id or "").strip()
                    if not sql_name:
                        continue
                    param_names = [str(param.name or "").strip() for param in sql.params if str(param.name or "").strip()]
                    for key in {sql_name, sql_id, f"{resource_id}:sql:{sql_name}"}:
                        if key:
                            naming_sql_name_by_key[key] = sql_name
                            naming_sql_param_names_by_key[key] = list(param_names)
                registry[resource_id] = BOResource(
                    resource_id=resource_id,
                    bo_name=bo.bo_name,
                    field_ids=field_ids,
                    data_source=data_source,
                    naming_sql_ids=naming_sql_ids,
                    naming_sql_name_by_key=naming_sql_name_by_key,
                    naming_sql_param_names_by_key=naming_sql_param_names_by_key,
                    scope=scope,
                    domain=bo.bo_name,
                    description=bo.description,
                    tags=[scope],
                )

        add_items(loaded.bo_registry.system_bos, "system")
        add_items(loaded.bo_registry.custom_bos, "custom")
        return registry

    def _normalize_functions(self, loaded: LoadedResources) -> dict[str, FunctionResource]:
        registry: dict[str, FunctionResource] = {}
        for row in loaded.function_payload.get("functions") or []:
            full_name = str(row.get("full_name") or row.get("name") or "").strip()
            if not full_name:
                continue
            resource_id = f"function:{full_name}"
            params = [str(p.get("name") or p.get("param_name") or "") for p in row.get("params") or [] if isinstance(p, dict)]
            if not params:
                params = [str(p) for p in row.get("params") or [] if isinstance(p, str)]
            signature = f"{full_name}({', '.join(params)})"
            registry[resource_id] = FunctionResource(
                resource_id=resource_id,
                function_id=str(row.get("id") or full_name),
                name=str(row.get("name") or full_name.split(".")[-1]),
                full_name=full_name,
                description=str(row.get("description") or ""),
                signature=signature,
                params=params,
                return_type=str((row.get("return_type") or {}).get("data_type_name") or ""),
                scope=str(row.get("source_type") or "func"),
                tags=[str(row.get("source_type") or "func")],
            )
        return registry
