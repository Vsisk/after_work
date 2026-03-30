from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from billing_dsl_agent.models import NormalizedTypeRef
from billing_dsl_agent.resource_models import (
    CandidateBO,
    CandidateContext,
    CandidateFunction,
    CandidateSet,
    ResourceIndexes,
)


class ResourceManager:
    """Build indexes and select compact candidate resources for prompt construction."""

    _DEFAULT_BUDGET: Dict[str, int] = {
        "context_candidates": 20,
        "bo_candidates": 10,
        "function_candidates": 10,
    }

    _ALIASES: Dict[str, Sequence[str]] = {
        "gender": ("sex", "性别"),
        "title": ("salutation", "称谓"),
        "amount": ("amt", "金额"),
        "billcycle": ("cycle", "账期"),
        "prepareid": ("prepare",),
    }

    def build_indexes(
        self,
        context_registry_or_vars: Any,
        bo_registry_or_list: Any,
        function_registry_or_list: Any,
    ) -> ResourceIndexes:
        context_by_path: Dict[str, Any] = {}
        context_by_name: Dict[str, List[Any]] = defaultdict(list)
        bo_by_name: Dict[str, Any] = {}
        bo_field_index: Dict[str, Dict[str, Any]] = defaultdict(dict)
        naming_sql_by_name: Dict[str, Any] = {}
        function_by_id: Dict[str, Any] = {}
        function_by_full_name: Dict[str, Any] = {}
        function_by_name: Dict[str, List[Any]] = defaultdict(list)

        for context in self._iter_contexts(context_registry_or_vars):
            path = self._context_path(context)
            if not path:
                continue
            context_by_path[path] = context
            name = self._context_name(context, path)
            if name:
                context_by_name[self._norm(name)].append(context)

        for bo in self._iter_items(bo_registry_or_list, ("bo", "bos", "items")):
            bo_name = self._first_text(bo, "bo_name", "name", "id")
            if not bo_name:
                continue
            bo_by_name[self._norm(bo_name)] = bo
            for field_name in self._bo_fields(bo):
                bo_field_index[self._norm(field_name)][self._norm(bo_name)] = bo
            for sql_name in self._bo_naming_sql_names(bo):
                naming_sql_by_name[self._norm(sql_name)] = bo

        for fn in self._iter_items(function_registry_or_list, ("functions", "func", "native_func", "items")):
            full_name = self._function_full_name(fn)
            if not full_name:
                continue
            function_id = self._first_text(fn, "function_id", "id", "resource_id")
            if function_id:
                function_by_id[self._norm(function_id)] = fn
            function_by_full_name[self._norm(full_name)] = fn
            function_by_name[self._norm(full_name.split(".")[-1])].append(fn)

        return ResourceIndexes(
            context_by_path=context_by_path,
            context_by_name=dict(context_by_name),
            bo_by_name=bo_by_name,
            bo_field_index=dict(bo_field_index),
            naming_sql_by_name=naming_sql_by_name,
            function_by_id=function_by_id,
            function_by_full_name=function_by_full_name,
            function_by_name=dict(function_by_name),
        )

    def normalize_functions(self, function_payload: Dict[str, Any]) -> Dict[str, Any]:
        version = str(function_payload.get("version", ""))
        normalized: List[Dict[str, Any]] = []

        for source_key, source_type in (("native_func", "native"), ("func", "custom")):
            class_rows = function_payload.get(source_key) or []
            if not isinstance(class_rows, list):
                continue
            for class_row in class_rows:
                if not isinstance(class_row, dict):
                    continue
                class_name = self._safe_text(class_row.get("class_name"))
                class_desc = self._safe_text(class_row.get("class_desc"))
                func_list = class_row.get("func_list") or []
                if not isinstance(func_list, list):
                    continue
                for func_row in func_list:
                    if not isinstance(func_row, dict):
                        continue
                    func_name = self._safe_text(func_row.get("func_name"))
                    if not func_name:
                        continue
                    func_id = self._safe_text(func_row.get("func_id"))
                    full_name = f"{class_name}.{func_name}" if class_name else func_name
                    normalized.append(
                        {
                            "id": func_id or full_name,
                            "name": func_name,
                            "full_name": full_name,
                            "class_name": class_name,
                            "class_desc": class_desc,
                            "description": self._safe_text(func_row.get("func_desc")) or class_desc,
                            "scope": self._safe_text(func_row.get("func_scope")) or ("global" if source_type == "native" else "custom"),
                            "source_type": source_type,
                            "function_kind": "native_func" if source_key == "native_func" else "func",
                            "shared_object": self._safe_text(func_row.get("func_so")),
                            "expression_type": self._safe_text((func_row.get("func_content") or {}).get("expression_type")),
                            "expression": self._safe_text((func_row.get("func_content") or {}).get("expression")),
                            "cdsl": self._safe_text((func_row.get("func_content") or {}).get("cdsl")),
                            "params": self._normalize_param_list(func_row.get("param_list")),
                            "return_type": self._normalize_return_type(func_row.get("return_type")),
                            "return_type_raw": self._extract_return_type_raw(func_row.get("return_type")),
                            "normalized_return_type_ref": asdict(
                                normalize_function_type(self._extract_return_type_raw(func_row.get("return_type")))
                            ),
                            "source_metadata": {
                                "source_key": source_key,
                                "class_name": class_name,
                                "scope": self._safe_text(func_row.get("func_scope")),
                            },
                            "raw_payload": dict(func_row),
                        }
                    )

        return {"version": version, "functions": normalized}

    def normalize_functions_to_file(self, function_payload: Dict[str, Any], output_path: str) -> Dict[str, Any]:
        normalized = self.normalize_functions(function_payload)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return normalized

    def select_candidates(
        self,
        user_query: str,
        node_def: Any,
        indexes: ResourceIndexes,
        budget: Optional[dict] = None,
    ) -> CandidateSet:
        active_budget = dict(self._DEFAULT_BUDGET)
        if isinstance(budget, dict):
            active_budget.update({k: int(v) for k, v in budget.items() if k in active_budget and isinstance(v, int)})

        candidate_set = CandidateSet()
        context_scores: Dict[str, CandidateContext] = {}
        bo_scores: Dict[str, CandidateBO] = {}
        fn_scores: Dict[str, CandidateFunction] = {}

        node_terms = self._keyword_set(" ".join(self._node_texts(node_def)))
        query_terms = self._keyword_set(user_query)

        self._score_contexts(node_terms, indexes, context_scores, candidate_set.selection_trace, stage="node")
        self._score_bos(node_terms, indexes, bo_scores, candidate_set.selection_trace, stage="node")
        self._score_functions(node_terms, indexes, fn_scores, candidate_set.selection_trace, stage="node")

        self._score_contexts(query_terms, indexes, context_scores, candidate_set.selection_trace, stage="query")
        self._score_bos(query_terms, indexes, bo_scores, candidate_set.selection_trace, stage="query")
        self._score_functions(query_terms, indexes, fn_scores, candidate_set.selection_trace, stage="query")

        self._expand_context_children(context_scores, indexes)

        candidate_set.context_candidates = self._truncate_candidates(
            list(context_scores.values()),
            active_budget["context_candidates"],
            key_fn=lambda item: (item.score, item.path),
        )
        candidate_set.bo_candidates = self._truncate_candidates(
            list(bo_scores.values()),
            active_budget["bo_candidates"],
            key_fn=lambda item: (item.score, item.bo_name),
        )
        candidate_set.function_candidates = self._truncate_candidates(
            list(fn_scores.values()),
            active_budget["function_candidates"],
            key_fn=lambda item: (item.score, item.full_name),
        )
        return candidate_set

    def format_for_prompt(self, candidate_set: CandidateSet) -> Dict[str, Any]:
        return {
            "context_candidates": [
                {"path": item.path, "name": item.name, "description": item.description}
                for item in candidate_set.context_candidates
            ],
            "bo_candidates": [
                {
                    "bo_name": item.bo_name,
                    "description": item.description,
                    "fields": item.fields,
                    "naming_sqls": item.naming_sqls,
                }
                for item in candidate_set.bo_candidates
            ],
            "function_candidates": [
                {
                    "function_id": item.function_id,
                    "function_name": item.full_name,
                    "name": item.full_name,
                    "description": item.description,
                    "normalized_return_type": item.normalized_return_type,
                    "params": item.params,
                }
                for item in candidate_set.function_candidates
            ],
        }

    def build_candidate_prompt_payload(
        self,
        user_query: str,
        node_def: Any,
        context_registry_or_vars: Any,
        bo_registry_or_list: Any,
        function_registry_or_list: Any,
        budget: Optional[dict] = None,
    ) -> Dict[str, Any]:
        indexes = self.build_indexes(
            context_registry_or_vars=context_registry_or_vars,
            bo_registry_or_list=bo_registry_or_list,
            function_registry_or_list=function_registry_or_list,
        )
        candidate_set = self.select_candidates(
            user_query=user_query,
            node_def=node_def,
            indexes=indexes,
            budget=budget,
        )
        payload = self.format_for_prompt(candidate_set)
        payload["selection_trace"] = list(candidate_set.selection_trace)
        return payload

    def _score_contexts(
        self,
        terms: set[str],
        indexes: ResourceIndexes,
        scores: Dict[str, CandidateContext],
        trace: List[str],
        stage: str,
    ) -> None:
        if not terms:
            return
        for path, ctx in indexes.context_by_path.items():
            name = self._context_name(ctx, path)
            description = self._first_text(ctx, "description", "desc")
            score = self._match_score(terms, [name, path.split(".")[-1], description, path])
            if score <= 0:
                continue
            candidate = scores.get(path)
            if candidate is None:
                candidate = CandidateContext(path=path, name=name, description=description)
                scores[path] = candidate
            candidate.score += score
            trace.append(f"[{stage}] context:{path} +{score:.2f}")

    def _score_bos(
        self,
        terms: set[str],
        indexes: ResourceIndexes,
        scores: Dict[str, CandidateBO],
        trace: List[str],
        stage: str,
    ) -> None:
        if not terms:
            return
        for norm_name, bo in indexes.bo_by_name.items():
            bo_name = self._first_text(bo, "bo_name", "name", "id")
            description = self._first_text(bo, "description", "desc")
            fields = self._bo_fields(bo)
            naming_sqls = self._bo_naming_sql_defs(bo)
            naming_sql_names = [str(item.get("naming_sql_name") or "") for item in naming_sqls]
            score = self._match_score(terms, [bo_name, description, " ".join(fields), " ".join(naming_sql_names)])
            if score <= 0:
                continue
            candidate = scores.get(norm_name)
            if candidate is None:
                candidate = CandidateBO(
                    bo_name=bo_name,
                    description=description,
                    fields=fields,
                    naming_sqls=naming_sqls,
                )
                scores[norm_name] = candidate
            candidate.score += score
            trace.append(f"[{stage}] bo:{bo_name} +{score:.2f}")

    def _score_functions(
        self,
        terms: set[str],
        indexes: ResourceIndexes,
        scores: Dict[str, CandidateFunction],
        trace: List[str],
        stage: str,
    ) -> None:
        if not terms:
            return
        for norm_name, fn in indexes.function_by_full_name.items():
            full_name = self._function_full_name(fn)
            description = self._first_text(fn, "description", "func_desc", "desc")
            function_id = self._first_text(fn, "function_id", "id", "resource_id") or full_name
            function_name = self._first_text(fn, "name", "function_name", "func_name") or full_name.split(".")[-1]
            params = self._function_params(fn)
            param_names = [item.get("param_name", "") for item in params]
            score = self._match_score(terms, [full_name, full_name.split(".")[-1], description, " ".join(param_names)])
            if score <= 0:
                continue
            candidate = scores.get(norm_name)
            if candidate is None:
                candidate = CandidateFunction(
                    function_id=function_id,
                    function_name=function_name,
                    full_name=full_name,
                    description=description,
                    normalized_return_type=self._function_return_type(fn),
                    params=params,
                )
                scores[norm_name] = candidate
            candidate.score += score
            trace.append(f"[{stage}] function:{full_name} +{score:.2f}")

    def _expand_context_children(self, context_scores: Dict[str, CandidateContext], indexes: ResourceIndexes) -> None:
        base_paths = list(context_scores.keys())
        for path in base_paths:
            parent_depth = path.count(".")
            for ctx_path, ctx in indexes.context_by_path.items():
                if not ctx_path.startswith(path + "."):
                    continue
                if ctx_path.count(".") != parent_depth + 1:
                    continue
                if ctx_path in context_scores:
                    continue
                parent_score = context_scores[path].score
                context_scores[ctx_path] = CandidateContext(
                    path=ctx_path,
                    name=self._context_name(ctx, ctx_path),
                    description=self._first_text(ctx, "description", "desc"),
                    score=max(parent_score * 0.35, 0.1),
                    metadata={"expanded_from": path},
                )

    def _truncate_candidates(self, candidates: List[Any], limit: int, key_fn: Any) -> List[Any]:
        sorted_items = sorted(candidates, key=key_fn, reverse=True)
        return sorted_items[: max(limit, 0)]

    def _keyword_set(self, text: str) -> set[str]:
        raw_text = text or ""
        raw_lower = raw_text.lower()
        base = {self._norm(token) for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", raw_text)}
        base = {item for item in base if item and item not in {"and", "or", "the", "is", "to", "of", "a", "an"}}
        expanded = set(base)
        for key, values in self._ALIASES.items():
            key_norm = self._norm(key)
            values_norm = {self._norm(v) for v in values}
            aliases = {key_norm, *values_norm}

            if any(alias and alias in raw_lower for alias in aliases):
                expanded.update(aliases)
                continue

            for token in list(base):
                if token == key_norm or token in values_norm:
                    expanded.update(aliases)
                    break
        return expanded

    def _match_score(self, terms: set[str], texts: List[str]) -> float:
        score = 0.0
        for raw in texts:
            if not raw:
                continue
            norm_text = self._norm(raw)
            tokens = self._keyword_set(raw)
            for term in terms:
                if term == norm_text:
                    score += 8.0
                elif term in tokens:
                    score += 3.0
                elif norm_text.endswith(term):
                    score += 2.0
                elif term in norm_text:
                    score += 1.0
        return score

    def _node_texts(self, node_def: Any) -> List[str]:
        return [
            self._first_text(node_def, "node_name", "name"),
            self._first_text(node_def, "node_path", "path"),
            self._first_text(node_def, "description", "desc"),
        ]

    def _iter_contexts(self, context_registry_or_vars: Any) -> Iterable[Any]:
        if context_registry_or_vars is None:
            return []
        if isinstance(context_registry_or_vars, dict):
            keys = set(context_registry_or_vars.keys())
            for carrier in ("contexts", "vars", "items"):
                if carrier in keys:
                    return self._iter_contexts(context_registry_or_vars[carrier])
            if self._looks_like_context_schema(context_registry_or_vars):
                return self._contexts_from_schema(context_registry_or_vars)
            return list(context_registry_or_vars.values())
        if isinstance(context_registry_or_vars, (list, tuple, set)):
            return list(context_registry_or_vars)
        return [context_registry_or_vars]

    def _iter_items(self, data: Any, carrier_keys: Tuple[str, ...]) -> Iterable[Any]:
        if data is None:
            return []
        if isinstance(data, dict):
            for key in carrier_keys:
                if key in data:
                    payload = data[key]
                    if isinstance(payload, list):
                        items: List[Any] = []
                        for row in payload:
                            if isinstance(row, dict) and "func_list" in row and isinstance(row["func_list"], list):
                                items.extend(row["func_list"])
                            else:
                                items.append(row)
                        return items
                    if isinstance(payload, dict):
                        return list(payload.values())
            return list(data.values())
        if isinstance(data, (list, tuple, set)):
            items = []
            for row in data:
                if isinstance(row, dict) and "func_list" in row and isinstance(row["func_list"], list):
                    items.extend(row["func_list"])
                else:
                    items.append(row)
            return items
        return [data]

    def _looks_like_context_schema(self, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        for value in data.values():
            if isinstance(value, (dict, list)):
                return True
        return False

    def _contexts_from_schema(self, schema: Dict[str, Any], prefix: str = "$ctx$") -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for key, value in schema.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                rows.extend(self._contexts_from_schema(value, path))
            else:
                rows.append({"path": path, "name": key, "description": ""})
        return rows

    def _context_path(self, item: Any) -> str:
        path = self._first_text(item, "path", "context_path", "full_path")
        if not path:
            name = self._first_text(item, "name", "context_name", "id")
            if name:
                return f"$ctx$.{name}" if not name.startswith("$ctx$.") else name
            return ""
        if path.startswith("$ctx$."):
            return path
        if path.startswith("ctx."):
            return "$ctx$." + path[len("ctx.") :]
        if path.startswith("$"):
            return path
        return f"$ctx$.{path}"

    def _context_name(self, item: Any, fallback_path: str = "") -> str:
        name = self._first_text(item, "name", "context_name", "id")
        if name:
            return name
        if fallback_path:
            return fallback_path.split(".")[-1]
        return ""

    def _bo_fields(self, bo: Any) -> List[str]:
        raw = self._first_non_none(bo, "fields", "field_list", "columns")
        if isinstance(raw, list):
            values: List[str] = []
            for item in raw:
                if isinstance(item, str):
                    values.append(item)
                else:
                    values.append(self._first_text(item, "name", "field_name", "id"))
            return [value for value in values if value]
        return []

    def _bo_naming_sql_names(self, bo: Any) -> List[str]:
        return [str(item.get("naming_sql_name") or "") for item in self._bo_naming_sql_defs(bo) if item.get("naming_sql_name")]

    def _bo_naming_sql_defs(self, bo: Any) -> List[Dict[str, Any]]:
        raw = self._first_non_none(bo, "naming_sqls", "naming_sql", "namingSqls", "queries")
        if not isinstance(raw, list):
            return []
        values: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, str):
                values.append({"naming_sql_id": item, "naming_sql_name": item, "params": []})
                continue
            params = self._bo_naming_sql_params(item)
            values.append(
                {
                    "naming_sql_id": self._first_text(item, "naming_sql_id", "id", "resource_id", "name", "sql_name"),
                    "naming_sql_name": self._first_text(item, "naming_sql_name", "name", "sql_name", "id"),
                    "params": params,
                }
            )
        return [value for value in values if value.get("naming_sql_name")]

    def _bo_naming_sql_params(self, naming_sql: Any) -> List[Dict[str, Any]]:
        raw = self._first_non_none(naming_sql, "params", "param_list", "parameters")
        if not isinstance(raw, list):
            return []
        values: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            values.append(
                {
                    "param_name": self._first_text(item, "param_name", "name", "id"),
                    "data_type": self._first_text(item, "data_type"),
                    "data_type_name": self._first_text(item, "data_type_name"),
                    "is_list": self._first_non_none(item, "is_list"),
                }
            )
        return [value for value in values if value.get("param_name")]

    def _function_full_name(self, fn: Any) -> str:
        full_name = self._first_text(fn, "full_name", "name")
        if full_name:
            return full_name
        class_name = self._first_text(fn, "class_name")
        func_name = self._first_text(fn, "func_name", "function_name", "name", "id")
        if class_name and func_name and "." not in func_name:
            return f"{class_name}.{func_name}"
        return func_name

    def _function_params(self, fn: Any) -> List[Dict[str, str]]:
        raw = self._first_non_none(fn, "params", "param_list", "arguments")
        if isinstance(raw, list):
            values: List[Dict[str, str]] = []
            for item in raw:
                if isinstance(item, str):
                    normalized_ref = normalize_function_type(None)
                    values.append(
                        {
                            "param_name": item,
                            "param_type": normalized_ref.normalized_type,
                            "raw_type": "",
                        }
                    )
                else:
                    param_name = self._first_text(item, "name", "param_name", "id")
                    param_type_raw = self._first_text(item, "param_type_raw", "data_type", "type", "data_type_name")
                    normalized_ref = normalize_function_type(param_type_raw)
                    values.append(
                        {
                            "param_name": param_name,
                            "param_type": normalized_ref.normalized_type,
                            "raw_type": param_type_raw,
                        }
                    )
            return [value for value in values if value.get("param_name")]
        return []

    def _normalize_param_list(self, raw_params: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_params, list):
            return []
        params: List[Dict[str, Any]] = []
        for idx, row in enumerate(raw_params):
            if not isinstance(row, dict):
                continue
            param_name = self._safe_text(row.get("param_name")) or f"param_{idx}"
            param_type_raw = self._safe_text(row.get("data_type")) or self._safe_text(row.get("type")) or self._safe_text(
                row.get("data_type_name")
            )
            normalized_type_ref = normalize_function_type(param_type_raw)
            params.append(
                {
                    "param_id": self._safe_text(row.get("param_id")) or f"{param_name}:{idx}",
                    "param_name": param_name,
                    "param_type_raw": param_type_raw,
                    "normalized_param_type": normalized_type_ref.normalized_type,
                    "type_ref": asdict(normalized_type_ref),
                    "data_type": self._safe_text(row.get("data_type")),
                    "type": self._safe_text(row.get("type")),
                    "data_type_name": self._safe_text(row.get("data_type_name")),
                    "is_list": bool(row.get("is_list", False) or normalized_type_ref.is_list),
                    "item_type": normalized_type_ref.item_type,
                    "is_optional": row.get("is_optional"),
                    "is_output": bool(row.get("is_output", False)),
                    "raw_payload": dict(row),
                }
            )
        return params

    def _normalize_return_type(self, return_type: Any) -> Dict[str, Any]:
        raw_type = self._extract_return_type_raw(return_type)
        normalized_type = normalize_function_type(raw_type)
        if not isinstance(return_type, dict):
            return {"data_type": "", "data_type_name": raw_type, "is_list": normalized_type.is_list}
        return {
            "data_type": self._safe_text(return_type.get("data_type")),
            "data_type_name": self._safe_text(return_type.get("data_type_name")) or raw_type,
            "is_list": bool(return_type.get("is_list", False) or normalized_type.is_list),
        }

    def _extract_return_type_raw(self, return_type: Any) -> str:
        if isinstance(return_type, dict):
            return (
                self._safe_text(return_type.get("data_type_name"))
                or self._safe_text(return_type.get("data_type"))
                or self._safe_text(return_type.get("type"))
            )
        return self._safe_text(return_type)

    def _function_return_type(self, fn: Any) -> str:
        type_ref = self._first_non_none(fn, "return_type_ref", "normalized_return_type_ref")
        if isinstance(type_ref, dict):
            return self._safe_text(type_ref.get("normalized_type")) or "unknown"
        raw_return_type = self._extract_return_type_raw(self._first_non_none(fn, "return_type", "return_type_raw"))
        return normalize_function_type(raw_return_type).normalized_type

    def _first_text(self, item: Any, *keys: str) -> str:
        value = self._first_non_none(item, *keys)
        if isinstance(value, str):
            return value
        return ""

    def _first_non_none(self, item: Any, *keys: str) -> Any:
        if item is None:
            return None
        for key in keys:
            if isinstance(item, dict):
                if key in item and item[key] is not None:
                    return item[key]
            else:
                if hasattr(item, key):
                    attr_value = getattr(item, key)
                    if attr_value is not None:
                        return attr_value
        return None

    def _norm(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())

    def _safe_text(self, value: Any) -> str:
        return value if isinstance(value, str) else ""


def build_candidate_prompt_payload(
    user_query: str,
    node_def: Any,
    context_registry_or_vars: Any,
    bo_registry_or_list: Any,
    function_registry_or_list: Any,
    budget: Optional[dict] = None,
) -> Dict[str, Any]:
    manager = ResourceManager()
    return manager.build_candidate_prompt_payload(
        user_query=user_query,
        node_def=node_def,
        context_registry_or_vars=context_registry_or_vars,
        bo_registry_or_list=bo_registry_or_list,
        function_registry_or_list=function_registry_or_list,
        budget=budget,
    )


def normalize_function_type(type_value: str | None) -> NormalizedTypeRef:
    raw_type = (type_value or "").strip()
    if not raw_type:
        return NormalizedTypeRef(raw_type="", normalized_type="unknown", category="unknown", is_unknown=True)
    compact = re.sub(r"\s+", "", raw_type)
    lower = compact.lower()
    list_match = re.match(r"^(?:list|array)\s*(?:<|\[)\s*([a-z0-9_$.]+)\s*(?:>|\])$", lower)
    if list_match:
        item_raw = list_match.group(1)
        item_ref = normalize_function_type(item_raw)
        normalized_item = item_ref.normalized_type if not item_ref.is_unknown else item_raw
        return NormalizedTypeRef(
            raw_type=raw_type,
            normalized_type=f"list[{normalized_item}]",
            category="collection",
            is_list=True,
            item_type=normalized_item,
            is_unknown=False,
        )
    alias_map = {
        "int": "int",
        "integer": "int",
        "long": "long",
        "string": "string",
        "str": "string",
        "bool": "boolean",
        "boolean": "boolean",
        "float": "float",
        "double": "double",
        "map": "map",
    }
    normalized = alias_map.get(lower)
    if normalized:
        return NormalizedTypeRef(
            raw_type=raw_type,
            normalized_type=normalized,
            category="basic" if normalized not in {"map"} else "object",
            is_unknown=False,
        )
    return NormalizedTypeRef(
        raw_type=raw_type,
        normalized_type="unknown",
        category="unknown",
        is_unknown=True,
    )
