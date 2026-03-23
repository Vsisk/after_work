"""LLM-first planner that proposes a structured generation plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from billing_dsl_agent.services.openai_client_adapter import OpenAIClientAdapter
from billing_dsl_agent.services.prompt_assembler import PromptAssembler
from billing_dsl_agent.services.simple_requirement_parser import SimpleRequirementParser
from billing_dsl_agent.types.agent import PlanDraft
from billing_dsl_agent.types.common import ContextScope
from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef
from billing_dsl_agent.types.plan import ResolvedEnvironment


@dataclass(slots=True)
class LLMPlanner:
    """Create a structured execution plan, with local fallback when needed."""

    prompt_assembler: PromptAssembler
    client: OpenAIClientAdapter
    fallback_parser: SimpleRequirementParser
    model: str = "gpt-4.1-mini"

    _FIELD_ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "客户性别": ("gender", "sex", "customerGender", "custSex"),
        "gender": ("gender", "sex", "customerGender", "custSex"),
        "sex": ("sex", "gender", "custSex"),
        "客户名称": ("name", "customerName", "custName"),
        "name": ("name", "customerName", "custName"),
        "账期": ("billCycleId", "billCycle", "cycle", "iIrrBillCycle"),
        "prepareId": ("prepareId",),
        "billCycleId": ("billCycleId", "billCycle", "cycle"),
        "regionId": ("regionId", "regionCode"),
        "amount": ("amount", "amt", "money"),
    }

    def plan(self, user_requirement: str, node_def: NodeDef, env: ResolvedEnvironment) -> PlanDraft:
        payload = self.prompt_assembler.build_payload(
            user_requirement=user_requirement,
            node_def=node_def,
            env=env,
            model=self.model,
        )
        draft = self.client.create_plan_draft(payload)
        if draft is not None:
            return self._normalize_draft(draft)
        fallback_intent = self.fallback_parser.parse(user_requirement, node_def)
        return self.intent_to_plan_draft(fallback_intent, env)

    def draft_to_intent(self, plan_draft: PlanDraft, node_def: NodeDef, user_requirement: str) -> NodeIntent:
        source_types = self._infer_source_types(plan_draft)
        operations = self._infer_operations(plan_draft)
        return NodeIntent(
            raw_requirement=user_requirement,
            target_node_path=node_def.node_path,
            target_node_name=node_def.node_name,
            target_data_type=node_def.data_type,
            source_types=source_types,
            operations=operations,
            constraints=[],
            semantic_slots=dict(plan_draft.semantic_slots),
        )

    def intent_to_plan_draft(self, intent: NodeIntent, env: ResolvedEnvironment | None = None) -> PlanDraft:
        env = env or ResolvedEnvironment()
        bo_refs: list[dict[str, object]] = []
        bo_name = str(intent.semantic_slots.get("bo_name") or "").strip()
        if bo_name:
            bo_ref: dict[str, object] = {
                "bo_name": bo_name,
                "query_mode": intent.semantic_slots.get("query_mode", "select"),
            }
            target_field = str(intent.semantic_slots.get("target_field") or "").strip()
            if target_field:
                bo_ref["field"] = target_field
            bo_refs.append(bo_ref)

        semantic_slots = dict(intent.semantic_slots)
        context_refs = self._resolve_context_refs(intent, env)
        if "condition_ref" not in semantic_slots and context_refs:
            semantic_slots["condition_ref"] = context_refs[0]

        expression_pattern = self._infer_expression_pattern_from_intent(intent)
        raw_plan = {
            "fallback": True,
            "source_types": [item.value for item in intent.source_types],
            "operations": [item.op_type for item in intent.operations],
        }
        return PlanDraft(
            intent_summary=f"Fallback plan for {intent.target_node_path}",
            semantic_slots=semantic_slots,
            context_refs=context_refs,
            bo_refs=bo_refs,
            function_refs=self._extract_function_refs(intent),
            expression_pattern=expression_pattern,
            raw_plan=raw_plan,
        )

    @staticmethod
    def _normalize_draft(draft: PlanDraft) -> PlanDraft:
        bo_refs: list[dict[str, object]] = []
        for item in draft.bo_refs or []:
            if isinstance(item, dict):
                bo_refs.append(dict(item))
        return PlanDraft(
            intent_summary=draft.intent_summary,
            semantic_slots=dict(draft.semantic_slots or {}),
            context_refs=[str(item).strip() for item in draft.context_refs or [] if str(item).strip()],
            bo_refs=bo_refs,
            function_refs=[str(item).strip() for item in draft.function_refs or [] if str(item).strip()],
            expression_pattern=str(draft.expression_pattern or "").strip(),
            raw_plan=dict(draft.raw_plan or {}),
        )

    def _resolve_context_refs(self, intent: NodeIntent, env: ResolvedEnvironment) -> list[str]:
        refs: list[str] = []
        explicit_refs = intent.semantic_slots.get("context_refs") or []
        for value in explicit_refs:
            text = str(value).strip()
            if text:
                refs.append(text)

        hints = list(intent.semantic_slots.get("context_field_hints") or [])
        condition_hint = str(intent.semantic_slots.get("condition_field_hint") or "").strip()
        if condition_hint:
            hints.append(condition_hint)

        for hint in hints:
            resolved = self._resolve_context_hint(str(hint), env)
            if resolved:
                refs.append(resolved)

        return self._dedup_strings(refs)

    def _resolve_context_hint(self, hint: str, env: ResolvedEnvironment) -> str | None:
        probes = self._build_context_probes(hint)
        for scope, vars_ in (
            (ContextScope.GLOBAL, env.global_context_vars),
            (ContextScope.LOCAL, env.local_context_vars),
        ):
            prefix = "$ctx$" if scope == ContextScope.GLOBAL else "$local$"
            for var in vars_:
                for field in var.fields or []:
                    normalized_field = self._normalize_token(field.name)
                    if normalized_field in probes:
                        return f"{prefix}.{var.name}.{field.name}"
            for var in vars_:
                normalized_var = self._normalize_token(var.name)
                if normalized_var in probes:
                    return f"{prefix}.{var.name}"
        return None

    @staticmethod
    def _extract_function_refs(intent: NodeIntent) -> list[str]:
        function_name = str(intent.semantic_slots.get("function_name") or "").strip()
        return [function_name] if function_name else []

    @staticmethod
    def _infer_expression_pattern_from_intent(intent: NodeIntent) -> str:
        slots = intent.semantic_slots or {}
        if slots.get("conditional_mapping") or IntentSourceType.CONDITIONAL in intent.source_types:
            return "if(condition, true, false)"
        if slots.get("function_name"):
            return "function_call(value)"
        if slots.get("bo_name"):
            return "query(field)"
        return "direct_ref"

    @staticmethod
    def _infer_source_types(plan_draft: PlanDraft) -> list[IntentSourceType]:
        result: list[IntentSourceType] = []
        if plan_draft.context_refs:
            result.append(IntentSourceType.CONTEXT)
        if plan_draft.bo_refs:
            result.append(IntentSourceType.BO_QUERY)
        if plan_draft.function_refs:
            result.append(IntentSourceType.FUNCTION)
        if "if(" in str(plan_draft.expression_pattern or "").lower():
            result.append(IntentSourceType.CONDITIONAL)
        if plan_draft.expression_pattern:
            result.append(IntentSourceType.EXPRESSION)
        deduped: list[IntentSourceType] = []
        for item in result:
            if item not in deduped:
                deduped.append(item)
        return deduped

    @staticmethod
    def _infer_operations(plan_draft: PlanDraft) -> list[OperationIntent]:
        operations: list[OperationIntent] = []
        if plan_draft.context_refs:
            operations.append(
                OperationIntent(
                    op_type="use_context_refs",
                    description="Use explicit context refs proposed by plan.",
                    expected_inputs=list(plan_draft.context_refs),
                )
            )
        if plan_draft.bo_refs:
            operations.append(
                OperationIntent(
                    op_type="use_bo_refs",
                    description="Use explicit BO refs proposed by plan.",
                    expected_inputs=[str(item.get("bo_name", "")) for item in plan_draft.bo_refs],
                )
            )
        if plan_draft.function_refs:
            operations.append(
                OperationIntent(
                    op_type="use_function_refs",
                    description="Use explicit function refs proposed by plan.",
                    expected_inputs=list(plan_draft.function_refs),
                )
            )
        if not operations:
            operations.append(
                OperationIntent(
                    op_type="build_expression",
                    description="Build expression from explicit LLM plan.",
                    expected_inputs=[plan_draft.expression_pattern] if plan_draft.expression_pattern else [],
                )
            )
        return operations

    def _build_context_probes(self, hint: str) -> list[str]:
        normalized_hint = self._normalize_token(hint)
        probes = [normalized_hint]
        for alias in self._FIELD_ALIASES.get(hint, ()):
            probes.append(self._normalize_token(alias))
        for alias in self._FIELD_ALIASES.get(normalized_hint, ()):
            probes.append(self._normalize_token(alias))
        return self._dedup_strings([probe for probe in probes if probe])

    @staticmethod
    def _normalize_token(value: str) -> str:
        return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())

    @staticmethod
    def _dedup_strings(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result
