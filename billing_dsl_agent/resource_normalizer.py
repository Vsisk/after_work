from __future__ import annotations

from dataclasses import dataclass
from typing import List

from billing_dsl_agent.bo_models import BODef
from billing_dsl_agent.context_models import ContextPropertyDef, NormalizedContextNode
from billing_dsl_agent.models import (
    BOResource,
    ContextResource,
    FunctionParamResource,
    FunctionRegistry,
    FunctionResource,
    ResourceRegistry,
)
from billing_dsl_agent.resource_manager import normalize_function_type
from billing_dsl_agent.resource_loader import LoadedResources


@dataclass(slots=True)
class ResourceNormalizer:
    def normalize(self, loaded: LoadedResources) -> ResourceRegistry:
        contexts = self._normalize_global_contexts(loaded)
        bos = self._normalize_bos(loaded)
        functions, function_registry = self._normalize_functions(loaded)
        return ResourceRegistry(
            contexts=contexts,
            bos=bos,
            functions=functions,
            function_registry=function_registry,
            edsl_tree=dict(loaded.edsl_tree or {}),
        )

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

    def _normalize_functions(self, loaded: LoadedResources) -> tuple[dict[str, FunctionResource], FunctionRegistry]:
        registry: dict[str, FunctionResource] = {}
        functions_by_id: dict[str, FunctionResource] = {}
        functions_by_name: dict[str, list[FunctionResource]] = {}
        for row in loaded.function_payload.get("functions") or []:
            full_name = str(row.get("full_name") or row.get("name") or "").strip()
            if not full_name:
                continue
            function_id = str(row.get("id") or full_name)
            resource_id = f"function:{full_name}"
            param_defs: list[FunctionParamResource] = []
            for index, raw_param in enumerate(row.get("params") or []):
                if isinstance(raw_param, dict):
                    param_name = str(raw_param.get("param_name") or raw_param.get("name") or f"param_{index}")
                    param_type_raw = str(raw_param.get("param_type_raw") or raw_param.get("data_type") or raw_param.get("type") or "")
                    type_ref_payload = raw_param.get("type_ref")
                    normalized_ref = (
                        normalize_function_type(param_type_raw)
                        if not isinstance(type_ref_payload, dict)
                        else normalize_function_type(str(type_ref_payload.get("raw_type") or param_type_raw))
                    )
                    param_defs.append(
                        FunctionParamResource(
                            param_id=str(raw_param.get("param_id") or f"{function_id}:{index}"),
                            param_name=param_name,
                            param_type_raw=param_type_raw,
                            normalized_param_type=str(
                                raw_param.get("normalized_param_type") or normalized_ref.normalized_type or "unknown"
                            ),
                            type_ref=normalized_ref,
                            is_list=bool(raw_param.get("is_list", False) or normalized_ref.is_list),
                            item_type=raw_param.get("item_type") or normalized_ref.item_type,
                            is_optional=raw_param.get("is_optional"),
                            raw_payload=dict(raw_param),
                        )
                    )
                elif isinstance(raw_param, str):
                    unknown_type = normalize_function_type(None)
                    param_defs.append(
                        FunctionParamResource(
                            param_id=f"{function_id}:{index}",
                            param_name=raw_param,
                            param_type_raw="",
                            normalized_param_type=unknown_type.normalized_type,
                            type_ref=unknown_type,
                            is_list=False,
                            item_type=None,
                            is_optional=None,
                            raw_payload={"param_name": raw_param},
                        )
                    )
            param_names = [item.param_name for item in param_defs]
            signature = f"{full_name}({', '.join(param_names)})"
            signature_display = f"{full_name}(" + ", ".join(
                f"{item.param_name}:{item.normalized_param_type}" for item in param_defs
            ) + ")"
            return_type_raw = str(row.get("return_type_raw") or "")
            return_type_ref = normalize_function_type(return_type_raw)
            function_resource = FunctionResource(
                resource_id=resource_id,
                function_id=function_id,
                name=str(row.get("name") or full_name.split(".")[-1]),
                full_name=full_name,
                description=str(row.get("description") or ""),
                function_kind=str(row.get("function_kind") or str(row.get("source_type") or "func")),
                signature=signature,
                signature_display=signature_display,
                params=param_names,
                param_defs=param_defs,
                return_type_raw=return_type_raw,
                return_type=return_type_ref.normalized_type,
                return_type_ref=return_type_ref,
                source_metadata=dict(row.get("source_metadata") or {}),
                raw_payload=dict(row.get("raw_payload") or row),
                scope=str(row.get("source_type") or "func"),
                tags=[str(row.get("source_type") or "func")],
            )
            registry[resource_id] = function_resource
            functions_by_id[function_resource.resource_id] = function_resource
            functions_by_id[function_resource.function_id] = function_resource
            full_name_key = function_resource.full_name
            short_name_key = function_resource.name
            functions_by_name.setdefault(full_name_key, []).append(function_resource)
            functions_by_name.setdefault(short_name_key, []).append(function_resource)
        return registry, FunctionRegistry(functions_by_id=functions_by_id, functions_by_name=functions_by_name)
