from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from billing_dsl_agent.models import NodeDef


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
        raise NotImplementedError


@dataclass(slots=True)
class MockSemanticSelector(SemanticSelector):
    top_k: int = 5

    def select(
        self,
        task_type: str,
        node_info: NodeDef,
        user_query: str,
        candidate_summaries: Iterable[CandidateSummary],
    ) -> List[str]:
        terms = self._tokens(f"{node_info.node_name} {node_info.node_path} {node_info.description} {user_query} {task_type}")
        scored: list[tuple[float, str]] = []
        for item in candidate_summaries:
            text = " ".join([item.description, item.resource_id, *item.tags])
            item_terms = self._tokens(text)
            overlap = len(terms & item_terms)
            score = overlap + (0.01 * len(item_terms))
            if score > 0:
                scored.append((score, item.resource_id))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [resource_id for _, resource_id in scored[: self.top_k]]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.lower()) if token}
