from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Protocol

from billing_dsl_agent.resource_retrieval.schemas import ResourceDocument, RetrievalHit
from billing_dsl_agent.resource_retrieval.text_normalizer import DEFAULT_TEXT_NORMALIZER, TextNormalizer

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3EmbeddingClient:
    def __init__(self, model_name: str = "BAAI/bge-m3", fallback_dim: int = 128) -> None:
        self._model_name = model_name
        self._fallback_dim = fallback_dim
        self._model = None
        try:  # pragma: no cover
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(model_name)
        except Exception:
            self._model = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._model is not None:  # pragma: no cover
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return [list(map(float, row)) for row in embeddings]
        return [self._hash_embed(text) for text in texts]

    def _hash_embed(self, text: str) -> list[float]:
        vector = [0.0] * self._fallback_dim
        for token in (text or "").split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(0, len(digest), 2):
                bucket = digest[index] % self._fallback_dim
                value = ((digest[index + 1] / 255.0) * 2.0) - 1.0
                vector[bucket] += value
        return _normalize(vector)


class EmbeddingRetriever:
    def __init__(
        self,
        embedding_client: EmbeddingClient | None = None,
        text_normalizer: TextNormalizer | None = None,
    ) -> None:
        self._embedding_client = embedding_client or BgeM3EmbeddingClient()
        self._text_normalizer = text_normalizer or DEFAULT_TEXT_NORMALIZER
        self._documents_by_type: dict[str, list[ResourceDocument]] = {}
        self._vectors_by_type: dict[str, list[list[float]]] = {}
        self._indexes_by_type: dict[str, object] = {}

    def build(self, documents: list[ResourceDocument]) -> None:
        self._documents_by_type = defaultdict(list)
        self._vectors_by_type = defaultdict(list)
        self._indexes_by_type = {}
        for item in documents:
            self._documents_by_type[item.resource_type].append(item)
        for resource_type, docs in self._documents_by_type.items():
            texts = [self._text_normalizer.normalize_text(item.search_text) for item in docs]
            vectors = [_normalize(row) for row in self._embedding_client.embed_texts(texts)]
            self._vectors_by_type[resource_type] = vectors
            if not vectors or faiss is None:
                continue
            index = faiss.IndexFlatIP(len(vectors[0]))
            index.add(_to_faiss_matrix(vectors))
            self._indexes_by_type[resource_type] = index

    def search(self, query_text: str, top_k: int) -> list[RetrievalHit]:
        query_vector = _normalize(self._embedding_client.embed_texts([self._text_normalizer.normalize_text(query_text)])[0])
        hits: list[RetrievalHit] = []
        for resource_type, docs in self._documents_by_type.items():
            if not docs:
                continue
            scores: list[tuple[int, float]]
            if faiss is not None and resource_type in self._indexes_by_type:  # pragma: no cover
                distances, indices = self._indexes_by_type[resource_type].search(_to_faiss_matrix([query_vector]), top_k)
                scores = [
                    (int(index), float(score))
                    for index, score in zip(indices[0].tolist(), distances[0].tolist())
                    if index >= 0 and score > 0
                ]
            else:
                scores = [
                    (index, _dot(query_vector, vector))
                    for index, vector in enumerate(self._vectors_by_type.get(resource_type, []))
                ]
                scores = sorted(scores, key=lambda item: item[1], reverse=True)[:top_k]
                scores = [item for item in scores if item[1] > 0]
            for rank, (index, score) in enumerate(scores, start=1):
                doc = docs[index]
                doc_tokens = set(self._text_normalizer.tokenize(doc.search_text))
                matched_terms = [
                    token for token in self._text_normalizer.tokenize(query_text) if token in doc_tokens
                ]
                hits.append(
                    RetrievalHit(
                        resource_id=doc.resource_id,
                        resource_type=resource_type,
                        score=score,
                        rank=rank,
                        source="vector",
                        matched_terms=matched_terms,
                    )
                )
        hits.sort(key=lambda item: (item.resource_type, item.rank))
        return hits


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm <= 0:
        return vector
    return [item / norm for item in vector]


def _dot(left: list[float], right: list[float]) -> float:
    return float(sum(l * r for l, r in zip(left, right)))


def _to_faiss_matrix(vectors: list[list[float]]):  # pragma: no cover
    import array

    rows = len(vectors)
    cols = len(vectors[0]) if vectors else 0
    matrix = array.array("f", [0.0] * (rows * cols))
    offset = 0
    for row in vectors:
        for value in row:
            matrix[offset] = float(value)
            offset += 1
    return matrix
