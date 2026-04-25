from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any

from billing_dsl_agent.models import BOResource, ContextResource, FunctionResource, NodeDef
from billing_dsl_agent.resource_retrieval.bm25_retriever import BM25Retriever
from billing_dsl_agent.resource_retrieval.concept_extractor import ConceptExtractor
from billing_dsl_agent.resource_retrieval.document_builder import ResourceDocumentBuilder
from billing_dsl_agent.resource_retrieval.embedding_retriever import BgeM3EmbeddingClient, EmbeddingRetriever
from billing_dsl_agent.resource_retrieval.rrf_ranker import RRFRanker
from billing_dsl_agent.resource_retrieval.schemas import (
    ResourceCandidate,
    ResourceCandidateSet,
    ResourceDocument,
    ResourceIndexBundle,
)


class ResourceIndexCache:
    def __init__(self, max_size: int = 24) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, tuple[BM25Retriever, EmbeddingRetriever]] = OrderedDict()

    def get_or_build(
        self,
        site_id: str | None,
        project_id: str | None,
        resource_type: str,
        documents: list[ResourceDocument],
        embedding_client: BgeM3EmbeddingClient,
    ) -> tuple[str, BM25Retriever, EmbeddingRetriever]:
        resource_hash = self.compute_hash(documents)
        cache_key = "::".join([site_id or "", project_id or "", resource_type, resource_hash])
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            bm25_retriever, embedding_retriever = self._cache[cache_key]
            return resource_hash, bm25_retriever, embedding_retriever

        bm25_retriever = BM25Retriever()
        bm25_retriever.build(documents)
        embedding_retriever = EmbeddingRetriever(embedding_client=embedding_client)
        embedding_retriever.build(documents)
        self._cache[cache_key] = (bm25_retriever, embedding_retriever)
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return resource_hash, bm25_retriever, embedding_retriever

    @staticmethod
    def compute_hash(documents: list[ResourceDocument]) -> str:
        payload = [
            {
                "resource_id": item.resource_id,
                "resource_type": item.resource_type,
                "name": item.name,
                "description": item.description,
                "search_text": item.search_text,
                "return_type": item.return_type,
                "path": item.path,
                "domain": item.domain,
                "tags": list(item.tags),
            }
            for item in documents
        ]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class ResourceRetrievalPipeline:
    def __init__(
        self,
        concept_extractor: ConceptExtractor | None = None,
        document_builder: ResourceDocumentBuilder | None = None,
        ranker: RRFRanker | None = None,
        index_cache: ResourceIndexCache | None = None,
        embedding_client: BgeM3EmbeddingClient | None = None,
    ) -> None:
        self._concept_extractor = concept_extractor or ConceptExtractor()
        self._document_builder = document_builder or ResourceDocumentBuilder()
        self._ranker = ranker or RRFRanker()
        self._index_cache = index_cache or ResourceIndexCache()
        self._embedding_client = embedding_client or BgeM3EmbeddingClient()

    def build_indexes(
        self,
        contexts: list[ContextResource],
        bos: list[BOResource],
        functions: list[FunctionResource],
        site_id: str | None = None,
        project_id: str | None = None,
    ) -> ResourceIndexBundle:
        context_documents = self._document_builder.build_context_documents(contexts)
        bo_documents = self._document_builder.build_bo_documents(bos)
        function_documents = self._document_builder.build_function_documents(functions)

        bundle = ResourceIndexBundle(
            context_documents=context_documents,
            bo_documents=bo_documents,
            function_documents=function_documents,
            document_lookup={
                (item.resource_type, item.resource_id): item
                for item in [*context_documents, *bo_documents, *function_documents]
            },
        )
        for resource_type, documents in (
            ("context", context_documents),
            ("bo", bo_documents),
            ("function", function_documents),
        ):
            resource_hash, bm25_retriever, embedding_retriever = self._index_cache.get_or_build(
                site_id=site_id,
                project_id=project_id,
                resource_type=resource_type,
                documents=documents,
                embedding_client=self._embedding_client,
            )
            bundle.resource_hashes[resource_type] = resource_hash
            bundle.bm25_retrievers[resource_type] = bm25_retriever
            bundle.embedding_retrievers[resource_type] = embedding_retriever
        return bundle

    def select_candidates(
        self,
        user_query: str,
        node_def: NodeDef,
        indexes: ResourceIndexBundle,
        top_k_per_type: int = 20,
    ) -> ResourceCandidateSet:
        concepts = self._concept_extractor.extract(user_query, node_def)
        query_terms = concepts.query_terms()
        query_text = " ".join(query_terms) or f"{node_def.node_name} {node_def.description} {user_query}".strip()
        candidate_set = ResourceCandidateSet()
        candidate_set.debug.concepts = concepts

        for resource_type, documents in (
            ("context", indexes.context_documents),
            ("bo", indexes.bo_documents),
            ("function", indexes.function_documents),
        ):
            if documents:
                bm25_hits = [
                    item
                    for item in indexes.bm25_retrievers[resource_type].search(query_terms=query_terms, top_k=top_k_per_type)
                    if item.resource_type == resource_type
                ]
                vector_hits = [
                    item
                    for item in indexes.embedding_retrievers[resource_type].search(query_text=query_text, top_k=top_k_per_type)
                    if item.resource_type == resource_type
                ]
            else:
                bm25_hits = []
                vector_hits = []
            candidate_set.debug.bm25_hits[resource_type] = bm25_hits
            candidate_set.debug.vector_hits[resource_type] = vector_hits

            doc_lookup = {item.resource_id: item for item in documents}
            rrf_candidates = self._ranker.rank(
                resource_type=resource_type,
                documents=doc_lookup,
                bm25_hits=bm25_hits,
                vector_hits=vector_hits,
                node_def=node_def,
                top_k=top_k_per_type,
            )
            fallback = ""
            if not rrf_candidates and bm25_hits:
                rrf_candidates = self._hits_to_candidates(resource_type, bm25_hits[:top_k_per_type], doc_lookup)
                fallback = "bm25_top20"
            if not rrf_candidates:
                rrf_candidates = self._documents_to_candidates(resource_type, documents[:top_k_per_type])
                fallback = "eligible_top20"

            candidate_set.debug.rrf_candidates[resource_type] = rrf_candidates
            if fallback:
                candidate_set.debug.fallbacks[resource_type] = fallback
            candidate_set.selection_trace.append(
                f"{resource_type}: bm25={len(bm25_hits)} vector={len(vector_hits)} candidates={len(rrf_candidates)}"
            )
            setattr(candidate_set, f"{resource_type}_candidates", rrf_candidates[:top_k_per_type])
        return candidate_set

    def _hits_to_candidates(
        self,
        resource_type: str,
        hits: list[Any],
        doc_lookup: dict[str, ResourceDocument],
    ) -> list[ResourceCandidate]:
        candidates: list[ResourceCandidate] = []
        for hit in hits:
            document = doc_lookup.get(hit.resource_id)
            if document is None:
                continue
            candidates.append(
                ResourceCandidate(
                    resource_id=document.resource_id,
                    resource_type=resource_type,
                    name=document.name,
                    description=document.description,
                    search_text=document.search_text,
                    final_score=hit.score,
                    bm25_rank=hit.rank if hit.source == "bm25" else None,
                    vector_rank=hit.rank if hit.source == "vector" else None,
                    matched_terms=list(hit.matched_terms),
                    raw_ref=document.raw_ref,
                )
            )
        return candidates

    def _documents_to_candidates(
        self,
        resource_type: str,
        documents: list[ResourceDocument],
    ) -> list[ResourceCandidate]:
        return [
            ResourceCandidate(
                resource_id=item.resource_id,
                resource_type=resource_type,
                name=item.name,
                description=item.description,
                search_text=item.search_text,
                final_score=0.0,
                raw_ref=item.raw_ref,
            )
            for item in documents
        ]
