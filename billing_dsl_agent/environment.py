from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from billing_dsl_agent.bo_models import BODef
from billing_dsl_agent.bo_models import BORegistry
from billing_dsl_agent.context_loader import build_context_path_map
from billing_dsl_agent.context_models import ContextRegistry
from billing_dsl_agent.models import Environment as LegacyEnvironment
from billing_dsl_agent.models import GenerateDSLRequest
from billing_dsl_agent.schema_provider import FunctionRegistry, LoadedSchemas


@dataclass(slots=True)
class Environment:
    node_info: Dict[str, Any]
    node_path: str
    visible_global_context: List[str] = field(default_factory=list)
    visible_local_context: List[str] = field(default_factory=list)
    bo_registry: BORegistry = field(default_factory=BORegistry)
    function_registry: FunctionRegistry = field(default_factory=FunctionRegistry)

    @property
    def context_paths(self) -> List[str]:
        return [*self.visible_global_context, *self.visible_local_context]

    @property
    def bo_schema(self) -> Dict[str, List[str]]:
        schema: Dict[str, List[str]] = {}
        for bo in self.bo_registry.all_bos():
            schema[bo.bo_name] = [field.name for field in bo.fields]
        return schema

    @property
    def function_schema(self) -> List[Dict[str, Any]]:
        return list(self.function_registry.functions)

    def filtered_by_candidates(self, candidate_set: Any) -> "Environment":
        context_paths = {str(getattr(item, "path", "")) for item in list(getattr(candidate_set, "context_candidates", []) or [])}
        bo_names = {str(getattr(item, "bo_name", "")) for item in list(getattr(candidate_set, "bo_candidates", []) or [])}
        function_names = {
            str(getattr(item, "full_name", "") or getattr(item, "name", ""))
            for item in list(getattr(candidate_set, "function_candidates", []) or [])
        }

        all_bos: List[BODef] = [bo for bo in self.bo_registry.all_bos() if bo.bo_name in bo_names]
        filtered_functions = [
            fn
            for fn in self.function_registry.functions
            if str(fn.get("full_name") or fn.get("name") or "") in function_names
        ]

        return Environment(
            node_info=dict(self.node_info),
            node_path=self.node_path,
            visible_global_context=[path for path in self.visible_global_context if path in context_paths],
            visible_local_context=[path for path in self.visible_local_context if path in context_paths],
            bo_registry=BORegistry(system_bos=list(all_bos), custom_bos=[]),
            function_registry=FunctionRegistry(functions=filtered_functions),
        )


class NodeContextResolver:
    def resolve(self, node_info: Dict[str, Any], loaded_schemas: LoadedSchemas) -> Environment:
        context_registry = loaded_schemas.context_registry
        context_map = build_context_path_map(context_registry)
        global_paths = sorted(context_map.keys())

        node_path = self._extract_node_path(node_info)
        # TODO: refine local-context strategy when node-local context model is finalized.
        local_paths = self._select_local_context(node_path=node_path, context_registry=context_registry, context_map=context_map)

        return Environment(
            node_info=dict(node_info),
            node_path=node_path,
            visible_global_context=global_paths,
            visible_local_context=local_paths,
            bo_registry=loaded_schemas.bo_registry,
            function_registry=loaded_schemas.function_registry,
        )

    def _extract_node_path(self, node_info: Dict[str, Any]) -> str:
        for key in ("node_path", "parent_path", "path"):
            value = node_info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _select_local_context(
        self,
        node_path: str,
        context_registry: ContextRegistry,
        context_map: Dict[str, Any],
    ) -> List[str]:
        if not context_registry.local_roots:
            return []

        segments = {part for part in node_path.split(".") if part}
        matched: List[str] = []
        for path in context_map.keys():
            if not path.startswith("$ctx$."):
                continue
            leaf = path.split(".")[-1]
            if leaf in segments:
                matched.append(path)
        return sorted(set(matched))


class EnvironmentBuilder:
    def build_environment(self, request: GenerateDSLRequest) -> LegacyEnvironment:
        return LegacyEnvironment(
            context_paths=self._flatten_context_paths(request.context_schema),
            bo_schema={name: list(fields) for name, fields in request.bo_schema.items()},
            function_schema=list(request.function_schema),
            node_schema={
                "node_id": request.node_def.node_id,
                "node_path": request.node_def.node_path,
                "node_name": request.node_def.node_name,
                "data_type": request.node_def.data_type,
            },
            context_schema=dict(request.context_schema),
        )

    def _flatten_context_paths(self, schema: Dict[str, Any]) -> List[str]:
        results: List[str] = []

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    next_prefix = f"{prefix}.{key}" if prefix else key
                    walk(next_prefix, nested)
                return
            if prefix:
                results.append(f"$ctx$.{prefix}")

        walk("", schema)
        return results


def build_environment(request: GenerateDSLRequest) -> LegacyEnvironment:
    return EnvironmentBuilder().build_environment(request)
