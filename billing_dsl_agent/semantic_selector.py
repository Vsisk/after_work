from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol

from billing_dsl_agent.models import LLMErrorRecord, NodeDef, ResourceSelectionOutput
from billing_dsl_agent.services.prompt_manager import PromptManager
from billing_dsl_agent.services.structured_llm_executor import StructuredLLMExecutor


@dataclass(slots=True)
class CandidateSummary:
    resource_id: str
    description: str
    tags: List[str]


class SemanticSelector:
    def select(
        self,
        task_type: str,
        node_info: NodeDef,
        user_query: str,
        candidate_summaries: Iterable[CandidateSummary],
    ) -> List[str]:
        return self.select_with_debug(task_type, node_info, user_query, candidate_summaries).selected_ids

    def select_with_debug(
        self,
        task_type: str,
        node_info: NodeDef,
        user_query: str,
        candidate_summaries: Iterable[CandidateSummary],
    ) -> "SelectionResult":
        raise NotImplementedError


class OpenAISelectorClient(Protocol):
    def create_plan(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ...


@dataclass(slots=True)
class SelectionResult:
    selected_ids: List[str]
    candidate_ids: List[str] = field(default_factory=list)
    llm_errors: List[LLMErrorRecord] = field(default_factory=list)
    fallback_used: bool = False


@dataclass(slots=True)
class OpenAISemanticSelector(SemanticSelector):
    client: OpenAISelectorClient
    prompt_manager: PromptManager = field(default_factory=PromptManager)
    prompt_lang: str = "zh"
    prompt_key: str = "semantic_selector_prompt"
    default_top_k: int = 5

    def select_with_debug(
        self,
        task_type: str,
        node_info: NodeDef,
        user_query: str,
        candidate_summaries: Iterable[CandidateSummary],
    ) -> SelectionResult:
        candidates = list(candidate_summaries)
        if not candidates:
            return SelectionResult(selected_ids=[], candidate_ids=[])

        allowed = {item.resource_id for item in candidates}
        fallback_ids = [item.resource_id for item in candidates[: self.default_top_k]]
        candidate_ids = [item.resource_id for item in candidates]
        executor = StructuredLLMExecutor(
            client=self.client,
            prompt_manager=self.prompt_manager,
            default_lang=self.prompt_lang,
        )
        prompt_params = {
            "task_type": task_type,
            "user_query": user_query,
            "node_def_json": json.dumps(
                {
                    "node_id": node_info.node_id,
                    "node_name": node_info.node_name,
                    "node_path": node_info.node_path,
                    "description": node_info.description,
                },
                ensure_ascii=False,
            ),
            "candidate_list_json": json.dumps(
                [
                    {
                        "resource_id": item.resource_id,
                        "description": item.description,
                        "tags": list(item.tags),
                    }
                    for item in candidates
                ],
                ensure_ascii=False,
            ),
            "max_items": self.default_top_k,
        }
        execution = executor.execute(
            prompt_key=self.prompt_key,
            lang=self.prompt_lang,
            prompt_params=prompt_params,
            response_model=ResourceSelectionOutput,
            stage="semantic_select",
        )
        if execution.parsed is None:
            return SelectionResult(
                selected_ids=fallback_ids,
                candidate_ids=candidate_ids,
                llm_errors=list(execution.errors),
                fallback_used=True,
            )

        filtered = [item for item in execution.parsed.resource_id_list if item in allowed]
        if filtered:
            return SelectionResult(
                selected_ids=filtered[: self.default_top_k],
                candidate_ids=candidate_ids,
                llm_errors=list(execution.errors),
                fallback_used=False,
            )
        errors = list(execution.errors)
        errors.append(
            LLMErrorRecord(
                stage="semantic_select",
                code="empty_resource_selection",
                message="semantic selector returned no valid resource ids; fallback to rule-ranked candidates",
                raw_payload=execution.raw_payload,
            )
        )
        return SelectionResult(
            selected_ids=fallback_ids,
            candidate_ids=candidate_ids,
            llm_errors=errors,
            fallback_used=True,
        )

@dataclass(slots=True)
class MockSemanticSelector(SemanticSelector):
    top_k: int = 5

    def select_with_debug(
        self,
        task_type: str,
        node_info: NodeDef,
        user_query: str,
        candidate_summaries: Iterable[CandidateSummary],
    ) -> SelectionResult:
        candidates = list(candidate_summaries)
        terms = self._tokens(f"{node_info.node_name} {node_info.node_path} {node_info.description} {user_query} {task_type}")
        scored: list[tuple[float, str]] = []
        for item in candidates:
            text = " ".join([item.description, item.resource_id, *item.tags])
            item_terms = self._tokens(text)
            overlap = len(terms & item_terms)
            score = overlap + (0.01 * len(item_terms))
            if score > 0:
                scored.append((score, item.resource_id))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return SelectionResult(
            selected_ids=[resource_id for _, resource_id in scored[: self.top_k]],
            candidate_ids=[item.resource_id for item in candidates],
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.lower()) if token}
