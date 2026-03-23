"""Prompt assembly helpers for the LLM planning stage."""

from __future__ import annotations

from typing import Any, Dict, List

from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import ResolvedEnvironment


class PromptAssembler:
    """Build compact prompt payloads with resource summaries instead of full schema dumps."""

    def build_payload(
        self,
        user_requirement: str,
        node_def: NodeDef,
        env: ResolvedEnvironment,
        model: str = "gpt-4.1-mini",
    ) -> Dict[str, Any]:
        resource_summary = self._build_resource_summary(env)
        user_prompt = self._build_user_prompt(user_requirement, node_def, resource_summary)
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a billing DSL planning agent. Propose a strict JSON plan with fields: "
                        "intent_summary, semantic_slots, context_refs, bo_refs, function_refs, "
                        "expression_pattern, raw_plan. Use only provided resource summaries."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "metadata": {
                "node_path": node_def.node_path,
                "node_name": node_def.node_name,
                "resource_summary": resource_summary,
            },
        }

    def _build_user_prompt(
        self,
        user_requirement: str,
        node_def: NodeDef,
        resource_summary: Dict[str, List[str]],
    ) -> str:
        return (
            f"Requirement: {user_requirement}\n"
            f"Target node: {node_def.node_path} ({node_def.node_name})\n"
            f"Target type: {node_def.data_type.value}\n"
            f"Global context summary: {', '.join(resource_summary['global_context']) or 'none'}\n"
            f"Local context summary: {', '.join(resource_summary['local_context']) or 'none'}\n"
            f"BO summary: {', '.join(resource_summary['bos']) or 'none'}\n"
            f"Function summary: {', '.join(resource_summary['functions']) or 'none'}"
        )

    def _build_resource_summary(self, env: ResolvedEnvironment) -> Dict[str, List[str]]:
        return {
            "global_context": [
                self._format_context_var(var.name, [field.name for field in var.fields or []])
                for var in env.global_context_vars or []
            ],
            "local_context": [
                self._format_context_var(var.name, [field.name for field in var.fields or []])
                for var in env.local_context_vars or []
            ],
            "bos": [self._format_bo_summary(bo.name, [field.name for field in bo.fields[:5] or []]) for bo in env.available_bos or []],
            "functions": [fn.full_name for fn in env.available_functions or []],
        }

    @staticmethod
    def _format_context_var(name: str, fields: List[str]) -> str:
        compact_fields = ", ".join(field for field in fields[:5] if field)
        return f"{name}({compact_fields})" if compact_fields else name

    @staticmethod
    def _format_bo_summary(name: str, fields: List[str]) -> str:
        compact_fields = ", ".join(field for field in fields if field)
        return f"{name}({compact_fields})" if compact_fields else name
