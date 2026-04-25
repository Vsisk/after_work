from __future__ import annotations

import math
from collections import Counter, defaultdict

from billing_dsl_agent.resource_retrieval.schemas import ResourceDocument, RetrievalHit
from billing_dsl_agent.resource_retrieval.text_normalizer import DEFAULT_TEXT_NORMALIZER, TextNormalizer

try:
    from rank_bm25 import BM25Okapi  # type: ignore
except Exception:  # pragma: no cover
    BM25Okapi = None


class _SimpleBM25:
    def __init__(self, corpus_tokens: list[list[str]]) -> None:
        self._corpus_tokens = corpus_tokens
        self._doc_freq: dict[str, int] = defaultdict(int)
        self._doc_lengths = [len(item) for item in corpus_tokens]
        self._avgdl = sum(self._doc_lengths) / len(self._doc_lengths) if self._doc_lengths else 0.0
        for tokens in corpus_tokens:
            for token in set(tokens):
                self._doc_freq[token] += 1

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores: list[float] = []
        total_docs = max(len(self._corpus_tokens), 1)
        for tokens in self._corpus_tokens:
            token_counter = Counter(tokens)
            doc_length = len(tokens) or 1
            score = 0.0
            for token in query_tokens:
                tf = token_counter.get(token, 0)
                if tf <= 0:
                    continue
                df = self._doc_freq.get(token, 0)
                idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
                score += idf * (tf * 2.2) / (tf + 1.2 * (1 - 0.75 + 0.75 * doc_length / (self._avgdl or 1.0)))
            scores.append(score)
        return scores


class BM25Retriever:
    def __init__(self, text_normalizer: TextNormalizer | None = None) -> None:
        self._text_normalizer = text_normalizer or DEFAULT_TEXT_NORMALIZER
        self._documents_by_type: dict[str, list[ResourceDocument]] = {}
        self._tokens_by_type: dict[str, list[list[str]]] = {}
        self._indexes_by_type: dict[str, BM25Okapi | _SimpleBM25] = {}

    def build(self, documents: list[ResourceDocument]) -> None:
        self._documents_by_type = defaultdict(list)
        self._tokens_by_type = defaultdict(list)
        self._indexes_by_type = {}
        for item in documents:
            self._documents_by_type[item.resource_type].append(item)
        for resource_type, docs in self._documents_by_type.items():
            corpus_tokens = [self._text_normalizer.tokenize(item.search_text) for item in docs]
            self._tokens_by_type[resource_type] = corpus_tokens
            self._indexes_by_type[resource_type] = BM25Okapi(corpus_tokens) if BM25Okapi is not None else _SimpleBM25(corpus_tokens)

    def search(self, query_terms: list[str], top_k: int) -> list[RetrievalHit]:
        normalized_query_terms = self._text_normalizer.tokenize(" ".join(item for item in query_terms if item))
        hits: list[RetrievalHit] = []
        for resource_type, docs in self._documents_by_type.items():
            if not docs:
                continue
            scores = list(self._indexes_by_type[resource_type].get_scores(normalized_query_terms))
            if not any(score > 0 for score in scores):
                scores = list(_SimpleBM25(self._tokens_by_type[resource_type]).get_scores(normalized_query_terms))
            ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
            rank = 1
            for index, score in ranked:
                if score <= 0:
                    continue
                doc_tokens = set(self._tokens_by_type[resource_type][index])
                matched_terms = [item for item in normalized_query_terms if item in doc_tokens]
                hits.append(
                    RetrievalHit(
                        resource_id=docs[index].resource_id,
                        resource_type=resource_type,
                        score=float(score),
                        rank=rank,
                        source="bm25",
                        matched_terms=matched_terms,
                    )
                )
                rank += 1
                if rank > top_k:
                    break
        hits.sort(key=lambda item: (item.resource_type, item.rank))
        return hits
