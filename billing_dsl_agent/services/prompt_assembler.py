"""Prompt assembly helpers for LLM-facing agent entrypoints."""

from __future__ import annotations

from typing import Any, Dict, List

from billing_dsl_agent.types.request_response import GenerateDSLRequest


class PromptAssembler:
    """Build prompt payloads for requirement understanding."""

    def build_payload(self, request: GenerateDSLRequest, model: str = "gpt-4.1-mini") -> Dict[str, Any]:
        resource_summary = self._build_resource_summary(request)
        user_prompt = self._build_user_prompt(request, resource_summary)
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You convert billing DSL requirements into a compact structured planning draft. "
                        "Return intent summary, semantic slots, candidate resources, source types, operations, "
                        "and expression pattern."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "metadata": {
                "node_path": request.node_def.node_path,
                "node_name": request.node_def.node_name,
                "resource_summary": resource_summary,
            },
        }

    def _build_user_prompt(self, request: GenerateDSLRequest, resource_summary: Dict[str, List[str]]) -> str:
        return (
            f"Requirement: {request.user_requirement}\n"
            f"Target node: {request.node_def.node_path} ({request.node_def.node_name})\n"
            f"Target type: {request.node_def.data_type.value}\n"
            f"Global context: {', '.join(resource_summary['global_context']) or 'none'}\n"
            f"Local context: {', '.join(resource_summary['local_context']) or 'none'}\n"
            f"BOs: {', '.join(resource_summary['bos']) or 'none'}\n"
            f"Functions: {', '.join(resource_summary['functions']) or 'none'}"
        )

    def _build_resource_summary(self, request: GenerateDSLRequest) -> Dict[str, List[str]]:
        return {
            "global_context": [
                self._format_context_var(var.name, [field.name for field in var.fields or []])
                for var in request.global_context_vars or []
            ],
            "local_context": [
                self._format_context_var(var.name, [field.name for field in var.fields or []])
                for var in request.local_context_vars or []
            ],
            "bos": [bo.name for bo in request.available_bos or []],
            "functions": [fn.full_name for fn in request.available_functions or []],
        }

    @staticmethod
    def _format_context_var(name: str, fields: List[str]) -> str:
        field_text = ", ".join(field for field in fields if field)
        return f"{name}({field_text})" if field_text else name
