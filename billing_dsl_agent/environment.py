from __future__ import annotations

from typing import Any, Dict, List

from billing_dsl_agent.models import Environment, GenerateDSLRequest


class EnvironmentBuilder:
    def build_environment(self, request: GenerateDSLRequest) -> Environment:
        return Environment(
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


def build_environment(request: GenerateDSLRequest) -> Environment:
    return EnvironmentBuilder().build_environment(request)
