from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
            for sql_name in self._bo_naming_sqls(bo):
                naming_sql_by_name[self._norm(sql_name)] = bo

        for fn in self._iter_items(function_registry_or_list, ("functions", "func", "native_func", "items")):
            full_name = self._function_full_name(fn)
            if not full_name:
                continue
            function_by_full_name[self._norm(full_name)] = fn
            function_by_name[self._norm(full_name.split(".")[-1])].append(fn)

        return ResourceIndexes(
            context_by_path=context_by_path,
            context_by_name=dict(context_by_name),
            bo_by_name=bo_by_name,
            bo_field_index=dict(bo_field_index),
            naming_sql_by_name=naming_sql_by_name,
            function_by_full_name=function_by_full_name,
            function_by_name=dict(function_by_name),
        )

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
                    "name": item.full_name,
                    "description": item.description,
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
            naming_sqls = self._bo_naming_sqls(bo)
            score = self._match_score(terms, [bo_name, description, " ".join(fields), " ".join(naming_sqls)])
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
            params = self._function_params(fn)
            score = self._match_score(terms, [full_name, full_name.split(".")[-1], description, " ".join(params)])
            if score <= 0:
                continue
            candidate = scores.get(norm_name)
            if candidate is None:
                candidate = CandidateFunction(full_name=full_name, description=description, params=params)
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

    def _bo_naming_sqls(self, bo: Any) -> List[str]:
        raw = self._first_non_none(bo, "naming_sqls", "naming_sql", "namingSqls", "queries")
        if isinstance(raw, list):
            values: List[str] = []
            for item in raw:
                if isinstance(item, str):
                    values.append(item)
                else:
                    values.append(self._first_text(item, "name", "sql_name", "id"))
            return [value for value in values if value]
        return []

    def _function_full_name(self, fn: Any) -> str:
        full_name = self._first_text(fn, "full_name", "name")
        if full_name:
            return full_name
        class_name = self._first_text(fn, "class_name")
        func_name = self._first_text(fn, "func_name", "function_name", "name", "id")
        if class_name and func_name and "." not in func_name:
            return f"{class_name}.{func_name}"
        return func_name

    def _function_params(self, fn: Any) -> List[str]:
        raw = self._first_non_none(fn, "params", "param_list", "arguments")
        if isinstance(raw, list):
            values: List[str] = []
            for item in raw:
                if isinstance(item, str):
                    values.append(item)
                else:
                    values.append(self._first_text(item, "name", "param_name", "id"))
            return [value for value in values if value]
        return []

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
