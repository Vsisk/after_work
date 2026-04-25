from __future__ import annotations

from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.resource_retrieval.schemas import ResourceCandidate, ResourceDocument, RetrievalHit


class RRFRanker:
    def __init__(self, k: int = 60) -> None:
        self._k = k

    def rank(
        self,
        resource_type: str,
        documents: dict[str, ResourceDocument],
        bm25_hits: list[RetrievalHit],
        vector_hits: list[RetrievalHit],
        node_def: NodeDef,
        top_k: int,
    ) -> list[ResourceCandidate]:
        scored: dict[str, dict[str, object]] = {}
        for hit in bm25_hits:
            row = scored.setdefault(
                hit.resource_id,
                {"bm25_rank": None, "vector_rank": None, "matched_terms": set(), "rrf_score": 0.0},
            )
            row["bm25_rank"] = hit.rank
            row["rrf_score"] = float(row["rrf_score"]) + self._rrf_score(hit.rank)
            row["matched_terms"] = set(row["matched_terms"]) | set(hit.matched_terms)
        for hit in vector_hits:
            row = scored.setdefault(
                hit.resource_id,
                {"bm25_rank": None, "vector_rank": None, "matched_terms": set(), "rrf_score": 0.0},
            )
            row["vector_rank"] = hit.rank
            row["rrf_score"] = float(row["rrf_score"]) + self._rrf_score(hit.rank)
            row["matched_terms"] = set(row["matched_terms"]) | set(hit.matched_terms)

        candidates: list[ResourceCandidate] = []
        for resource_id, row in scored.items():
            document = documents.get(resource_id)
            if document is None:
                continue
            final_score = (
                float(row["rrf_score"])
                + self._resource_type_weight(resource_type)
                + self._node_type_weight(node_def, resource_type, document)
                + self._local_context_weight(node_def, document)
                + self._history_success_weight(resource_id)
            )
            candidates.append(
                ResourceCandidate(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    name=document.name,
                    description=document.description,
                    search_text=document.search_text,
                    final_score=final_score,
                    bm25_rank=row["bm25_rank"],
                    vector_rank=row["vector_rank"],
                    matched_terms=sorted(set(row["matched_terms"])),
                    raw_ref=document.raw_ref,
                )
            )
        candidates.sort(
            key=lambda item: (
                item.final_score,
                1 if item.bm25_rank is not None and item.vector_rank is not None else 0,
                -min(item.bm25_rank or 9999, item.vector_rank or 9999),
                item.name,
            ),
            reverse=True,
        )
        return candidates[:top_k]

    def _rrf_score(self, rank: int) -> float:
        return 1.0 / (self._k + rank)

    def _resource_type_weight(self, resource_type: str) -> float:
        return {"context": 0.03, "bo": 0.02, "function": 0.02}.get(resource_type, 0.0)

    def _node_type_weight(self, node_def: NodeDef, resource_type: str, document: ResourceDocument) -> float:
        node_name = (node_def.node_name or "").lower()
        if node_name and node_name in document.search_text:
            return 0.02
        if resource_type == "function" and "rule" in node_name:
            return -0.01
        return 0.0

    def _local_context_weight(self, node_def: NodeDef, document: ResourceDocument) -> float:
        node_path = (node_def.node_path or "").lower()
        if node_path and document.name.lower() in node_path:
            return 0.01
        return 0.0

    def _history_success_weight(self, resource_id: str) -> float:
        return 0.0
