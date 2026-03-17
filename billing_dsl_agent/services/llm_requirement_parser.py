"""LLM-facing requirement parser with simple-parser fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from billing_dsl_agent.services.openai_client_adapter import OpenAIClientAdapter
from billing_dsl_agent.services.prompt_assembler import PromptAssembler
from billing_dsl_agent.services.simple_requirement_parser import SimpleRequirementParser
from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.request_response import GenerateDSLRequest


@dataclass(slots=True)
class LLMRequirementParser:
    """Convert LLM plan drafts into NodeIntent, with local fallback."""

    prompt_assembler: PromptAssembler
    client: OpenAIClientAdapter
    fallback_parser: SimpleRequirementParser
    model: str = "gpt-4.1-mini"

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        return self.fallback_parser.parse(user_requirement, node_def)

    def parse_request(self, request: GenerateDSLRequest) -> NodeIntent:
        payload = self.prompt_assembler.build_payload(request, model=self.model)
        draft = self.client.create_plan_draft(payload)
        if draft is None:
            return self.fallback_parser.parse(request.user_requirement, request.node_def)
        return self._draft_to_intent(request, draft)

    def _draft_to_intent(self, request: GenerateDSLRequest, draft: PlanDraft) -> NodeIntent:
        source_types = self._coerce_source_types(draft.source_types)
        operations = self._coerce_operations(draft.operations, draft.expression_pattern)

        return NodeIntent(
            raw_requirement=request.user_requirement,
            target_node_path=request.node_def.node_path,
            target_node_name=request.node_def.node_name,
            target_data_type=request.node_def.data_type,
            source_types=source_types,
            operations=operations,
            constraints=[],
            semantic_slots=dict(draft.semantic_slots),
        )

    @staticmethod
    def _coerce_source_types(values: list[str]) -> list[IntentSourceType]:
        result: list[IntentSourceType] = []
        for value in values or []:
            normalized = str(value or "").strip().upper()
            try:
                source_type = IntentSourceType[normalized]
            except KeyError:
                continue
            if source_type not in result:
                result.append(source_type)
        return result

    @staticmethod
    def _coerce_operations(values: list[str], expression_pattern: str) -> list[OperationIntent]:
        operations: list[OperationIntent] = []
        for value in values or []:
            op_type = str(value or "").strip()
            if not op_type:
                continue
            if any(existing.op_type == op_type for existing in operations):
                continue
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description=f"LLM draft operation: {op_type}",
                    expected_inputs=[expression_pattern] if expression_pattern else [],
                )
            )
        if not operations and expression_pattern:
            operations.append(
                OperationIntent(
                    op_type="build_expression",
                    description=f"LLM draft expression pattern: {expression_pattern}",
                    expected_inputs=[expression_pattern],
                )
            )
        return operations
