from __future__ import annotations

from dataclasses import dataclass
from typing import List

from billing_dsl_agent.bo_models import (
    BODef,
    NormalizedNamingSQLDef,
    NormalizedNamingSQLParam,
    NormalizedNamingTypeRef,
)
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
                if not child.children:
                    resource_id = f"context:{path}"
                    domain = path.split(".")[1] if "." in path else "default"
                    registry[resource_id] = ContextResource(
                        resource_id=resource_id,
                        name=child.name,
                        path=path,
                        scope="global",
                        domain=domain,
                        description=child.description,
                        tags=["context_json", child.metadata.get("raw_value_source_type", ""), "leaf_only"],
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
            if not path or not node.is_leaf:
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
                tags=["context_json", node.context_kind, node.source_type, "leaf_only"],
            )

    def _normalize_bos(self, loaded: LoadedResources) -> dict[str, BOResource]:
        registry: dict[str, BOResource] = {}

        def add_items(items: List[BODef], scope: str) -> None:
            for bo in items:
                resource_id = f"bo:{bo.bo_name}"
                field_ids = [f"{resource_id}:field:{field.name}" for field in bo.fields]
                naming_sql_ids: list[str] = []
                naming_sql_name_by_key: dict[str, str] = {}
                naming_sql_param_names_by_key: dict[str, list[str]] = {}
                naming_sql_signature_by_key: dict[str, dict[str, object]] = {}
                naming_sql_param_meta_by_key: dict[str, list[dict[str, object]]] = {}
                naming_sql_defs: list[dict[str, object]] = []
                data_source = ""
                for sql in bo.query_capability.naming_sqls:
                    ds = str(sql.metadata.get("or_mapping_data_source") or "")
                    if ds:
                        data_source = ds
                    sql_name = str(sql.name or "").strip()
                    sql_id = str(sql.id or "").strip()
                    if not sql_name:
                        continue
                    naming_sql_ids.append(f"{resource_id}:sql:{sql_name}")
                    if sql_id:
                        naming_sql_ids.append(sql_id)
                    normalized_sql = self._normalize_naming_sql(bo_id=resource_id, sql=sql)
                    param_names = [param.param_name for param in normalized_sql.params if param.param_name]
                    param_meta = [
                        {
                            "param_id": param.param_id,
                            "param_name": param.param_name,
                            "data_type": param.data_type,
                            "data_type_name": param.data_type_name,
                            "is_list": param.is_list,
                            "normalized_type_ref": {
                                "data_type": param.normalized_type_ref.data_type,
                                "data_type_name": param.normalized_type_ref.data_type_name,
                                "is_list": param.normalized_type_ref.is_list,
                                "is_unknown": param.normalized_type_ref.is_unknown,
                            },
                            "raw_payload": dict(param.raw_payload),
                        }
                        for param in normalized_sql.params
                    ]
                    signature = {
                        "naming_sql_id": normalized_sql.naming_sql_id,
                        "naming_sql_name": normalized_sql.naming_sql_name,
                        "bo_id": normalized_sql.bo_id,
                        "description": normalized_sql.description,
                        "sql": normalized_sql.sql,
                        "signature_display": normalized_sql.signature_display,
                        "params": param_meta,
                        "raw_payload": dict(normalized_sql.raw_payload),
                    }
                    naming_sql_defs.append(dict(signature))
                    for key in {sql_name, sql_id, f"{resource_id}:sql:{sql_name}"}:
                        if key:
                            naming_sql_name_by_key[key] = sql_name
                            naming_sql_param_names_by_key[key] = list(param_names)
                            naming_sql_signature_by_key[key] = dict(signature)
                            naming_sql_param_meta_by_key[key] = list(param_meta)
                registry[resource_id] = BOResource(
                    resource_id=resource_id,
                    bo_name=bo.bo_name,
                    field_ids=field_ids,
                    data_source=data_source,
                    naming_sql_ids=naming_sql_ids,
                    naming_sql_defs=naming_sql_defs,
                    naming_sql_name_by_key=naming_sql_name_by_key,
                    naming_sql_param_names_by_key=naming_sql_param_names_by_key,
                    naming_sql_signature_by_key=naming_sql_signature_by_key,
                    naming_sql_param_meta_by_key=naming_sql_param_meta_by_key,
                    scope=scope,
                    domain=bo.bo_name,
                    description=bo.description,
                    tags=[scope],
                )

        add_items(loaded.bo_registry.system_bos, "system")
        add_items(loaded.bo_registry.custom_bos, "custom")
        return registry

    def _normalize_naming_sql(self, bo_id: str, sql: object) -> NormalizedNamingSQLDef:
        sql_id = str(getattr(sql, "id", "") or "").strip()
        sql_name = str(getattr(sql, "name", "") or "").strip()
        description = str(getattr(sql, "description", "") or "").strip()
        sql_text = str(getattr(sql, "sql", "") or "").strip()
        params: list[NormalizedNamingSQLParam] = []
        for index, param in enumerate(list(getattr(sql, "params", []) or [])):
            raw_payload = dict(getattr(param, "metadata", {}).get("raw_payload") or {})
            param_name = str(getattr(param, "name", "") or "").strip()
            type_ref_obj = getattr(param, "type_ref", None)
            data_type = str(getattr(type_ref_obj, "data_type", "") or "").strip()
            data_type_name = str(getattr(type_ref_obj, "data_type_name", "") or "").strip()
            raw_is_list = raw_payload.get("is_list")
            if isinstance(raw_is_list, bool):
                is_list: bool | None = raw_is_list
            else:
                type_ref_list = getattr(type_ref_obj, "is_list", None)
                is_list = type_ref_list if isinstance(type_ref_list, bool) else None
            type_ref = NormalizedNamingTypeRef(
                data_type=data_type,
                data_type_name=data_type_name,
                is_list=is_list,
                is_unknown=not (data_type and data_type_name and isinstance(is_list, bool)),
            )
            param_id = f"{sql_id or sql_name or bo_id}:param:{param_name or index}"
            params.append(
                NormalizedNamingSQLParam(
                    param_id=param_id,
                    param_name=param_name,
                    data_type=data_type,
                    data_type_name=data_type_name,
                    is_list=is_list,
                    normalized_type_ref=type_ref,
                    raw_payload=raw_payload,
                )
            )

        signature_parts = []
        for param in params:
            list_mark = "[]" if param.is_list else ""
            unknown_mark = "?" if param.normalized_type_ref.is_unknown else ""
            signature_parts.append(
                f"{param.param_name}:{param.data_type}.{param.data_type_name}{list_mark}{unknown_mark}".strip(":")
            )
        signature_display = f"{sql_name or sql_id}({', '.join(signature_parts)})"
        return NormalizedNamingSQLDef(
            naming_sql_id=sql_id,
            naming_sql_name=sql_name,
            bo_id=bo_id,
            description=description,
            sql=sql_text,
            params=params,
            signature_display=signature_display,
            raw_payload={
                "metadata": dict(getattr(sql, "metadata", {}) or {}),
                "label": str(getattr(sql, "label", "") or ""),
            },
        )

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
