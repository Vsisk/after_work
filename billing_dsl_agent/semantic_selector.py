from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from typing import Any, Dict, Optional, Protocol

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


class OpenAISelectorClient(Protocol):
    def create_plan(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ...


@dataclass(slots=True)
class OpenAISemanticSelector(SemanticSelector):
    client: OpenAISelectorClient
    prompt_path: Path = Path(__file__).resolve().parent / "prompts" / "semantic_selector_prompt.json"
    default_top_k: int = 5

    def select(
        self,
        task_type: str,
        node_info: NodeDef,
        user_query: str,
        candidate_summaries: Iterable[CandidateSummary],
    ) -> List[str]:
        candidates = list(candidate_summaries)
        if not candidates:
            return []

        prompt = self._load_prompt()
        payload = {
            "mode": "semantic_select",
            "system_prompt": prompt.get("system", ""),
            "instruction": prompt.get("instruction", ""),
            "input": {
                "task_type": task_type,
                "user_query": user_query,
                "node_def": {
                    "node_id": node_info.node_id,
                    "node_name": node_info.node_name,
                    "node_path": node_info.node_path,
                    "description": node_info.description,
                },
                "candidate_list": [
                    {
                        "resource_id": item.resource_id,
                        "description": item.description,
                        "tags": list(item.tags),
                    }
                    for item in candidates
                ],
                "budget": {"max_items": self.default_top_k},
            },
            "output_format": {"resource_id_list": []},
        }
        raw = self.client.create_plan(payload)
        resource_ids = self._parse_output(raw)
        if not resource_ids:
            return []

        allowed = {item.resource_id for item in candidates}
        filtered = [item for item in resource_ids if item in allowed]
        return filtered[: self.default_top_k]

    def _load_prompt(self) -> Dict[str, str]:
        try:
            data = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"system": "", "instruction": ""}
        if not isinstance(data, dict):
            return {"system": "", "instruction": ""}
        return {str(k): str(v) for k, v in data.items()}

    def _parse_output(self, raw: Optional[Dict[str, Any]]) -> List[str]:
        if not isinstance(raw, dict):
            return []

        output = raw.get("resource_id_list")
        if isinstance(output, list):
            return [str(item) for item in output if isinstance(item, str)]

        raw_output = raw.get("output")
        if isinstance(raw_output, str):
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError:
                return []
            if isinstance(parsed, dict):
                ids = parsed.get("resource_id_list")
                if isinstance(ids, list):
                    return [str(item) for item in ids if isinstance(item, str)]
        return []


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
