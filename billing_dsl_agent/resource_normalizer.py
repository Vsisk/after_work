from __future__ import annotations

from dataclasses import dataclass
from typing import List

from billing_dsl_agent.bo_models import BODef
from billing_dsl_agent.context_models import ContextPropertyDef
from billing_dsl_agent.models import BOResource, ContextResource, FunctionResource, ResourceRegistry
from billing_dsl_agent.resource_loader import LoadedResources


@dataclass(slots=True)
class ResourceNormalizer:
    def normalize(self, loaded: LoadedResources) -> ResourceRegistry:
        contexts = self._normalize_contexts(loaded)
        bos = self._normalize_bos(loaded)
        functions = self._normalize_functions(loaded)
        return ResourceRegistry(contexts=contexts, bos=bos, functions=functions)

    def _normalize_contexts(self, loaded: LoadedResources) -> dict[str, ContextResource]:
        registry: dict[str, ContextResource] = {}
        root = loaded.context_registry.global_root
        if root is None:
            return registry

        local_ids: set[str] = set()
        for local_root in loaded.context_registry.local_roots:
            self._collect_context_ids(local_root, local_ids)

        def walk(node: ContextPropertyDef, parent_path: str) -> None:
            for index, child in enumerate(node.children):
                segment = child.name or child.id or f"node{index}"
                path = f"{parent_path}.{segment}" if parent_path else segment
                resource_id = f"context:{path}"
                scope = "local" if child.id in local_ids else "global"
                domain = path.split(".")[1] if "." in path else "default"
                registry[resource_id] = ContextResource(
                    resource_id=resource_id,
                    name=child.name,
                    path=path,
                    scope=scope,
                    domain=domain,
                    description=child.description,
                    tags=[child.metadata.get("raw_value_source_type", "")],
                )
                walk(child, path)

        walk(root, "$ctx$")
        return registry

    def _collect_context_ids(self, node: ContextPropertyDef, bucket: set[str]) -> None:
        bucket.add(node.id)
        for child in node.children:
            self._collect_context_ids(child, bucket)

    def _normalize_bos(self, loaded: LoadedResources) -> dict[str, BOResource]:
        registry: dict[str, BOResource] = {}

        def add_items(items: List[BODef], scope: str) -> None:
            for bo in items:
                resource_id = f"bo:{bo.bo_name}"
                field_ids = [f"{resource_id}:field:{field.name}" for field in bo.fields]
                naming_sql_ids = [f"{resource_id}:sql:{sql.name}" for sql in bo.query_capability.naming_sqls if sql.name]
                data_source = ""
                for sql in bo.query_capability.naming_sqls:
                    ds = str(sql.metadata.get("or_mapping_data_source") or "")
                    if ds:
                        data_source = ds
                        break
                registry[resource_id] = BOResource(
                    resource_id=resource_id,
                    bo_name=bo.bo_name,
                    field_ids=field_ids,
                    data_source=data_source,
                    naming_sql_ids=naming_sql_ids,
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
