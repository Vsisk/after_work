from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(slots=True)
class CandidateContext:
    path: str
    name: str
    description: str = ""
    score: float = 0.0
    source: str = "context"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateBO:
    bo_name: str
    description: str = ""
    fields: List[str] = field(default_factory=list)
    naming_sqls: List[Dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    source: str = "bo"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateFunction:
    function_id: str
    function_name: str
    full_name: str
    description: str = ""
    normalized_return_type: str = ""
    params: List[Dict[str, str]] = field(default_factory=list)
    score: float = 0.0
    source: str = "function"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateSet:
    context_candidates: List[CandidateContext] = field(default_factory=list)
    bo_candidates: List[CandidateBO] = field(default_factory=list)
    function_candidates: List[CandidateFunction] = field(default_factory=list)
    selection_trace: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ResourceIndexes:
    context_by_path: Dict[str, Any] = field(default_factory=dict)
    context_by_name: Dict[str, List[Any]] = field(default_factory=dict)
    bo_by_name: Dict[str, Any] = field(default_factory=dict)
    bo_field_index: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    naming_sql_by_name: Dict[str, Any] = field(default_factory=dict)
    function_by_id: Dict[str, Any] = field(default_factory=dict)
    function_by_full_name: Dict[str, Any] = field(default_factory=dict)
    function_by_name: Dict[str, List[Any]] = field(default_factory=dict)
