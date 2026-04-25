from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from billing_dsl_agent.log_utils import get_logger
from billing_dsl_agent.models import LLMErrorRecord, NodeDef, ResourceSelectionOutput
from billing_dsl_agent.services.llm_client import OpenAILLMClient

logger = get_logger(__name__)


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


@dataclass(slots=True)
class SelectionResult:
    selected_ids: List[str]
    candidate_ids: List[str] = field(default_factory=list)
    llm_errors: List[LLMErrorRecord] = field(default_factory=list)
    fallback_used: bool = False
    debug_info: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OpenAISemanticSelector(SemanticSelector):
    client: OpenAILLMClient | Any
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
            logger.info(
                "semantic_selection_skipped task_type=%s node_id=%s reason=no_candidates",
                task_type,
                node_info.node_id,
            )
            return SelectionResult(selected_ids=[], candidate_ids=[])

        allowed = {item.resource_id for item in candidates}
        fallback_ids = [item.resource_id for item in candidates[: self.default_top_k]]
        candidate_ids = [item.resource_id for item in candidates]
        logger.info(
            "semantic_selection_started task_type=%s node_id=%s candidate_count=%s fallback_ids=%s",
            task_type,
            node_info.node_id,
            len(candidates),
            fallback_ids,
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
        execution = self.client.execute_structured(
            prompt_key=self.prompt_key,
            lang=self.prompt_lang,
            prompt_params=prompt_params,
            response_model=ResourceSelectionOutput,
            stage="semantic_select",
        )
        if execution.parsed is None:
            logger.warning(
                "semantic_selection_fallback task_type=%s reason=parse_failed errors=%s",
                task_type,
                [item.code for item in execution.errors],
            )
            return SelectionResult(
                selected_ids=fallback_ids,
                candidate_ids=candidate_ids,
                llm_errors=list(execution.errors),
                fallback_used=True,
            )

        filtered = [item for item in execution.parsed.resource_id_list if item in allowed]
        if filtered:
            logger.info(
                "semantic_selection_completed task_type=%s selected_ids=%s",
                task_type,
                filtered[: self.default_top_k],
            )
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
        selected_ids = [resource_id for _, resource_id in scored[: self.top_k]]
        logger.info(
            "mock_semantic_selection_completed task_type=%s node_id=%s selected_ids=%s",
            task_type,
            node_info.node_id,
            selected_ids,
        )
        return SelectionResult(
            selected_ids=selected_ids,
            candidate_ids=[item.resource_id for item in candidates],
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.lower()) if token}
