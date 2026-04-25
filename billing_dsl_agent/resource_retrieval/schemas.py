from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal


@dataclass(slots=True)
class ExtractedConcepts:
    keywords: list[str]
    noun_phrases: list[str]
    domain_terms: list[str]
    aliases: dict[str, list[str]] = field(default_factory=dict)

    def query_terms(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in [*self.keywords, *self.noun_phrases, *self.domain_terms]:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        for alias_terms in self.aliases.values():
            for item in alias_terms:
                if item and item not in seen:
                    seen.add(item)
                    ordered.append(item)
        return ordered


@dataclass(slots=True)
class ResourceDocument:
    resource_id: str
    resource_type: Literal["context", "bo", "function"]
    name: str
    description: str
    search_text: str
    return_type: str = ""
    path: str = ""
    domain: str = "default"
    tags: list[str] = field(default_factory=list)
    raw_ref: Any = None


@dataclass(slots=True)
class RetrievalHit:
    resource_id: str
    resource_type: str
    score: float
    rank: int
    source: Literal["bm25", "vector"]
    matched_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResourceCandidate:
    resource_id: str
    resource_type: str
    name: str
    description: str
    search_text: str
    final_score: float
    bm25_rank: int | None = None
    vector_rank: int | None = None
    matched_terms: list[str] = field(default_factory=list)
    raw_ref: Any = None

    @property
    def path(self) -> str:
        return _get_value(self.raw_ref, "path", "context_path", "full_path", default="")

    @property
    def bo_name(self) -> str:
        return _get_value(self.raw_ref, "bo_name", "name", default=self.name)

    @property
    def function_name(self) -> str:
        return _get_value(self.raw_ref, "function_name", "name", "func_name", default=self.name)

    @property
    def full_name(self) -> str:
        return _get_value(self.raw_ref, "full_name", "name", default=self.function_name)

    @property
    def function_id(self) -> str:
        return _get_value(self.raw_ref, "function_id", "id", "resource_id", default=self.resource_id)

    @property
    def fields(self) -> list[str]:
        fields = _get_list(self.raw_ref, "field_ids", "fields")
        if fields:
            return [str(item) for item in fields]
        return [
            _get_value(item, "field_name", "name", "id", default="")
            for item in _get_list(self.raw_ref, "property_list")
            if _get_value(item, "field_name", "name", "id", default="")
        ]

    @property
    def naming_sqls(self) -> list[Any]:
        result: list[Any] = []
        naming_sqls = _get_list(self.raw_ref, "naming_sqls")
        if not naming_sqls:
            for mapping in _get_list(self.raw_ref, "or_mapping_list"):
                naming_sqls.extend(_get_list(mapping, "naming_sql_list"))
        for item in naming_sqls:
            params = []
            for param in _get_list(item, "params", "param_list"):
                params.append(
                    {
                        "param_name": _get_value(param, "param_name", "name", "id", default=""),
                        "data_type": _get_value(param, "data_type", default=""),
                        "data_type_name": _get_value(param, "data_type_name", "type", default=""),
                        "is_list": _get_value(param, "is_list", default=None),
                    }
                )
            result.append(
                {
                    "naming_sql_id": _get_value(item, "naming_sql_id", "id", default=""),
                    "naming_sql_name": _get_value(item, "naming_sql_name", "sql_name", "name", default=""),
                    "params": params,
                }
            )
        return result

    @property
    def normalized_return_type(self) -> str:
        return _get_value(self.raw_ref, "return_type", "return_type_raw", default="")

    @property
    def params(self) -> list[Any]:
        param_defs = getattr(self.raw_ref, "param_defs", [])
        if param_defs:
            return [
                {
                    "param_name": getattr(item, "param_name", ""),
                    "param_type": getattr(item, "normalized_param_type", ""),
                    "raw_type": getattr(item, "param_type_raw", ""),
                }
                for item in param_defs
            ]
        raw_params = _get_list(self.raw_ref, "params", "param_list")
        return list(raw_params)


@dataclass(slots=True)
class RetrievalDebugInfo:
    concepts: ExtractedConcepts | None = None
    bm25_hits: dict[str, list[RetrievalHit]] = field(default_factory=dict)
    vector_hits: dict[str, list[RetrievalHit]] = field(default_factory=dict)
    rrf_candidates: dict[str, list[ResourceCandidate]] = field(default_factory=dict)
    final_selected_ids: dict[str, list[str]] = field(default_factory=dict)
    fallbacks: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "concepts": None
            if self.concepts is None
            else {
                "keywords": list(self.concepts.keywords),
                "noun_phrases": list(self.concepts.noun_phrases),
                "domain_terms": list(self.concepts.domain_terms),
                "aliases": {key: list(value) for key, value in self.concepts.aliases.items()},
            },
            "bm25_hits": {
                key: [
                    {
                        "resource_id": item.resource_id,
                        "resource_type": item.resource_type,
                        "score": item.score,
                        "rank": item.rank,
                        "source": item.source,
                        "matched_terms": list(item.matched_terms),
                    }
                    for item in value
                ]
                for key, value in self.bm25_hits.items()
            },
            "vector_hits": {
                key: [
                    {
                        "resource_id": item.resource_id,
                        "resource_type": item.resource_type,
                        "score": item.score,
                        "rank": item.rank,
                        "source": item.source,
                        "matched_terms": list(item.matched_terms),
                    }
                    for item in value
                ]
                for key, value in self.vector_hits.items()
            },
            "rrf_candidates": {
                key: [
                    {
                        "resource_id": item.resource_id,
                        "resource_type": item.resource_type,
                        "name": item.name,
                        "description": item.description,
                        "final_score": item.final_score,
                        "bm25_rank": item.bm25_rank,
                        "vector_rank": item.vector_rank,
                        "matched_terms": list(item.matched_terms),
                    }
                    for item in value
                ]
                for key, value in self.rrf_candidates.items()
            },
            "final_selected_ids": {key: list(value) for key, value in self.final_selected_ids.items()},
            "fallbacks": dict(self.fallbacks),
        }


@dataclass(slots=True)
class ResourceCandidateSet:
    context_candidates: list[ResourceCandidate] = field(default_factory=list)
    bo_candidates: list[ResourceCandidate] = field(default_factory=list)
    function_candidates: list[ResourceCandidate] = field(default_factory=list)
    debug: RetrievalDebugInfo = field(default_factory=RetrievalDebugInfo)
    selection_trace: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResourceIndexBundle:
    context_documents: list[ResourceDocument] = field(default_factory=list)
    bo_documents: list[ResourceDocument] = field(default_factory=list)
    function_documents: list[ResourceDocument] = field(default_factory=list)
    document_lookup: dict[tuple[str, str], ResourceDocument] = field(default_factory=dict)
    bm25_retrievers: dict[str, Any] = field(default_factory=dict)
    embedding_retrievers: dict[str, Any] = field(default_factory=dict)
    resource_hashes: dict[str, str] = field(default_factory=dict)

    @property
    def context_by_path(self) -> dict[str, Any]:
        return {item.path: item.raw_ref for item in self.context_documents if item.path}

    @property
    def context_by_name(self) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = {}
        for item in self.context_documents:
            grouped.setdefault(_norm_key(item.name), []).append(item.raw_ref)
        return grouped

    @property
    def bo_by_name(self) -> dict[str, Any]:
        return {_norm_key(item.name): item.raw_ref for item in self.bo_documents}

    @property
    def bo_field_index(self) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in self.bo_documents:
            raw = item.raw_ref
            fields = _get_list(raw, "field_ids", "fields")
            if not fields:
                fields = [
                    _get_value(entry, "field_name", "name", "id", default="")
                    for entry in _get_list(raw, "property_list")
                ]
            for field_name in fields:
                grouped.setdefault(_norm_key(str(field_name)), {})[_norm_key(item.name)] = raw
        return grouped

    @property
    def naming_sql_by_name(self) -> dict[str, Any]:
        grouped: dict[str, Any] = {}
        for item in self.bo_documents:
            raw = item.raw_ref
            naming_sqls = _get_list(raw, "naming_sqls")
            if not naming_sqls:
                for mapping in _get_list(raw, "or_mapping_list"):
                    naming_sqls.extend(_get_list(mapping, "naming_sql_list"))
            for naming_sql in naming_sqls:
                name = _get_value(naming_sql, "naming_sql_name", "sql_name", "name", default="") or ""
                key = _norm_key(name)
                if key:
                    grouped[key] = raw
        return grouped

    @property
    def function_by_id(self) -> dict[str, Any]:
        grouped: dict[str, Any] = {}
        for item in self.function_documents:
            raw = item.raw_ref
            key = _get_value(raw, "function_id", "id", "resource_id", default=item.resource_id)
            grouped[_norm_key(str(key))] = raw
        return grouped

    @property
    def function_by_full_name(self) -> dict[str, Any]:
        grouped: dict[str, Any] = {}
        for item in self.function_documents:
            raw = item.raw_ref
            key = _get_value(raw, "full_name", "name", default=item.name)
            grouped[_norm_key(str(key))] = raw
        return grouped

    @property
    def function_by_name(self) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = {}
        for item in self.function_documents:
            raw = item.raw_ref
            key = _norm_key(str(item.name.split(".")[-1]))
            grouped.setdefault(key, []).append(raw)
        return grouped


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (value or "").lower())


def _get_value(resource: Any, *keys: str, default: Any = "") -> Any:
    for key in keys:
        if isinstance(resource, dict) and key in resource and resource[key] is not None:
            return resource[key]
        if hasattr(resource, key):
            value = getattr(resource, key)
            if value is not None:
                return value
    return default


def _get_list(resource: Any, *keys: str) -> list[Any]:
    value = _get_value(resource, *keys, default=[])
    return value if isinstance(value, list) else []
