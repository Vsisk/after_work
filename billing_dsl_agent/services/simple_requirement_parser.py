"""Rule-based mock requirement parser for MVP usage."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef

_ZH_GLOBAL_CONTEXT = "\u5168\u5c40\u4e0a\u4e0b\u6587"
_ZH_CURRENT = "\u5f53\u524d"
_ZH_LOCAL_CONTEXT = "\u5c40\u90e8\u4e0a\u4e0b\u6587"
_ZH_LOCAL_VAR = "\u5c40\u90e8\u53d8\u91cf"
_ZH_QUERY = "\u67e5\u8be2"
_ZH_LOOKUP = "\u67e5\u8868"
_ZH_FORMAT = "\u683c\u5f0f\u5316"
_ZH_IF = "\u5982\u679c"
_ZH_ELSE = "\u5426\u5219"
_ZH_JUDGE = "\u5224\u65ad"
_ZH_WHEN = "\u5f53"
_ZH_CONCAT = "\u62fc\u63a5"
_ZH_CALC = "\u8ba1\u7b97"
_ZH_EXPR = "\u8868\u8fbe\u5f0f"
_ZH_TWO_DECIMAL = "\u4e24\u4f4d\u5c0f\u6570"
_ZH_FIRST = "\u7b2c\u4e00\u6761"
_ZH_NOT_NULL = "\u4e0d\u80fd\u4e3a\u7a7a"
_ZH_DEFAULT = "\u9ed8\u8ba4"
_ZH_CUSTOMER_GENDER = "\u5ba2\u6237\u6027\u522b"
_ZH_BILL_CYCLE = "\u8d26\u671f"
_ZH_MALE = "\u7537"


class SimpleRequirementParser:
    """Parse requirement text into NodeIntent with lightweight keyword rules."""

    _CONTEXT_KEYWORDS: Sequence[str] = ("$ctx$", "ctx", "context", _ZH_GLOBAL_CONTEXT, _ZH_CURRENT)
    _LOCAL_CONTEXT_KEYWORDS: Sequence[str] = ("$local$", "local", _ZH_LOCAL_CONTEXT, _ZH_LOCAL_VAR)
    _BO_QUERY_KEYWORDS: Sequence[str] = ("select", "select_one", _ZH_QUERY, _ZH_LOOKUP)
    _NAMING_SQL_KEYWORDS: Sequence[str] = ("fetch", "fetch_one", "naming sql", "namingsql")
    _FUNCTION_KEYWORDS: Sequence[str] = ("if", "exists", "concat", "merge_list", _ZH_FORMAT, "format")
    _CONDITIONAL_KEYWORDS: Sequence[str] = ("if", _ZH_IF, _ZH_ELSE, _ZH_JUDGE, _ZH_WHEN)
    _EXPRESSION_KEYWORDS: Sequence[str] = (_ZH_CONCAT, _ZH_CALC, _ZH_EXPR, "format", _ZH_FORMAT)

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        """Parse text requirement into a stable NodeIntent using simple rules."""

        raw_text = (user_requirement or "").strip()
        normalized_text = self._normalize_requirement_text(raw_text)

        semantic_slots = self._detect_semantic_slots(raw_text=raw_text, normalized_text=normalized_text)
        source_types = self._detect_source_types(
            raw_text=raw_text,
            normalized_text=normalized_text,
            semantic_slots=semantic_slots,
        )
        operations = self._detect_operations(
            raw_text=raw_text,
            normalized_text=normalized_text,
            source_types=source_types,
            semantic_slots=semantic_slots,
        )
        constraints = self._detect_constraints(raw_text=raw_text, normalized_text=normalized_text)

        return NodeIntent(
            raw_requirement=raw_text,
            target_node_path=node_def.node_path,
            target_node_name=node_def.node_name,
            target_data_type=node_def.data_type,
            source_types=source_types,
            operations=operations,
            constraints=constraints,
            semantic_slots=semantic_slots,
        )

    def _normalize_requirement_text(self, text: str) -> str:
        """Lowercase and collapse multi-space text for stable keyword matching."""

        return " ".join(text.lower().split())

    def _detect_semantic_slots(self, raw_text: str, normalized_text: str) -> Dict[str, Any]:
        """Extract lightweight semantic slots for planner/matcher usage."""

        slots: Dict[str, Any] = {}
        mapping = self._detect_conditional_mapping(raw_text)
        if mapping:
            slots.update(mapping)

        method_tokens = self._extract_function_like_tokens(raw_text)
        if method_tokens:
            slots["function_like_tokens"] = method_tokens

        field_candidates = self._extract_field_hint_candidates(raw_text)
        if field_candidates:
            slots["field_hint_candidates"] = field_candidates

        if _ZH_TWO_DECIMAL in raw_text or "2\u4f4d\u5c0f\u6570" in raw_text or "two decimal" in normalized_text:
            slots["format_precision"] = 2

        if _ZH_FIRST in raw_text or "first" in normalized_text:
            slots["query_expect_first"] = True

        return slots

    def _detect_source_types(
        self,
        raw_text: str,
        normalized_text: str,
        semantic_slots: Dict[str, Any],
    ) -> List[IntentSourceType]:
        """Infer source types from requirement keywords and function-like tokens."""

        source_types: List[IntentSourceType] = []

        if self._contains_any(raw_text, normalized_text, self._CONTEXT_KEYWORDS):
            source_types.append(IntentSourceType.CONTEXT)
        if self._contains_any(raw_text, normalized_text, self._LOCAL_CONTEXT_KEYWORDS):
            source_types.append(IntentSourceType.LOCAL_CONTEXT)
        if self._contains_any(raw_text, normalized_text, self._BO_QUERY_KEYWORDS):
            source_types.append(IntentSourceType.BO_QUERY)
        if self._contains_any(raw_text, normalized_text, self._NAMING_SQL_KEYWORDS):
            source_types.append(IntentSourceType.NAMING_SQL)

        function_like_tokens = semantic_slots.get("function_like_tokens") or []
        if function_like_tokens or self._contains_any(raw_text, normalized_text, self._FUNCTION_KEYWORDS):
            source_types.append(IntentSourceType.FUNCTION)

        if self._contains_any(raw_text, normalized_text, self._EXPRESSION_KEYWORDS):
            source_types.append(IntentSourceType.EXPRESSION)
        if self._contains_any(raw_text, normalized_text, self._CONDITIONAL_KEYWORDS) or semantic_slots.get(
            "conditional_mapping"
        ):
            source_types.append(IntentSourceType.CONDITIONAL)

        return self._dedup_source_types(source_types)

    def _detect_operations(
        self,
        raw_text: str,
        normalized_text: str,
        source_types: Sequence[IntentSourceType],
        semantic_slots: Dict[str, Any],
    ) -> List[OperationIntent]:
        """Build operation intents from detected source types and keywords."""

        operations: List[OperationIntent] = []

        if IntentSourceType.CONTEXT in source_types:
            operations.append(
                OperationIntent(
                    op_type="read_context",
                    description="Read value from global context.",
                    expected_inputs=["context_path_or_name"],
                )
            )

        if IntentSourceType.LOCAL_CONTEXT in source_types:
            operations.append(
                OperationIntent(
                    op_type="read_local_context",
                    description="Read value from local context.",
                    expected_inputs=["local_context_path_or_name"],
                )
            )

        if IntentSourceType.BO_QUERY in source_types:
            op_type = "query_bo"
            if "select_one" in normalized_text or semantic_slots.get("query_expect_first"):
                op_type = "query_bo_select_one"
            elif "select" in normalized_text:
                op_type = "query_bo_select"
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description="Query BO resources.",
                    expected_inputs=["bo_name", "conditions"],
                )
            )

        if IntentSourceType.NAMING_SQL in source_types:
            op_type = "query_naming_sql"
            if "fetch_one" in normalized_text:
                op_type = "query_naming_sql_fetch_one"
            elif "fetch" in normalized_text:
                op_type = "query_naming_sql_fetch"
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description="Query naming sql resources.",
                    expected_inputs=["naming_sql_name", "params"],
                )
            )

        if IntentSourceType.FUNCTION in source_types:
            function_candidates = semantic_slots.get("function_like_tokens") or self._extract_function_like_tokens(raw_text)
            operations.append(
                OperationIntent(
                    op_type="call_function",
                    description="Call function candidate from requirement text.",
                    expected_inputs=function_candidates or ["function_name"],
                )
            )

        if IntentSourceType.EXPRESSION in source_types:
            operations.append(
                OperationIntent(
                    op_type="build_expression",
                    description="Build expression from requirement.",
                    expected_inputs=["expression_parts"],
                )
            )

        if IntentSourceType.CONDITIONAL in source_types:
            cond_op_type = "build_conditional_mapping" if semantic_slots.get("conditional_mapping") else "build_conditional"
            operations.append(
                OperationIntent(
                    op_type=cond_op_type,
                    description="Build conditional expression.",
                    expected_inputs=["condition", "true_expr", "false_expr"],
                )
            )

        if not operations:
            operations.append(
                OperationIntent(
                    op_type="interpret_requirement",
                    description="No explicit keyword matched; interpret plain requirement.",
                    expected_inputs=["requirement_text"],
                )
            )

        return self._dedup_operations(operations)

    def _detect_constraints(self, raw_text: str, normalized_text: str) -> List[str]:
        """Extract minimal constraints from obvious requirement hints."""

        constraints: List[str] = []
        if _ZH_NOT_NULL in raw_text or "not null" in normalized_text:
            constraints.append("result_must_not_be_null")
        if _ZH_DEFAULT in raw_text or "default" in normalized_text:
            constraints.append("should_have_default_fallback")
        return constraints

    def _detect_conditional_mapping(self, raw_text: str) -> Dict[str, Any]:
        """Detect conditional-mapping pattern and extract mapping slots."""

        quoted_literals = self._extract_quoted_literals(raw_text)
        case_matches = list(
            re.finditer(
                rf"{_ZH_WHEN}\s*(?P<field>[^为时，。,]+?)\s*为\s*(?P<value>[^时，。,\s]+)\s*时",
                raw_text,
            )
        )

        if len(case_matches) >= 2 and quoted_literals:
            first_case = case_matches[0]
            second_case = case_matches[1]
            true_output = quoted_literals[0] if len(quoted_literals) > 0 else ""
            false_output = quoted_literals[1] if len(quoted_literals) > 1 else ""
            return {
                "conditional_mapping": True,
                "condition_field_hint": self._clean_literal(first_case.group("field")),
                "condition_operator": "==",
                "condition_value": self._clean_literal(first_case.group("value")),
                "true_output": true_output,
                "false_output": false_output,
                "conditional_cases": [
                    {
                        "when": {
                            "field_hint": self._clean_literal(first_case.group("field")),
                            "operator": "==",
                            "value": self._clean_literal(first_case.group("value")),
                        },
                        "then": true_output,
                    },
                    {
                        "when": {
                            "field_hint": self._clean_literal(second_case.group("field")),
                            "operator": "==",
                            "value": self._clean_literal(second_case.group("value")),
                        },
                        "then": false_output,
                    },
                ],
            }

        match_if_else = re.search(
            rf"""(?:{_ZH_IF}|if)\s*
            (?P<field>[^，。,:]+?)\s*
            (?:为|是|==)\s*
            (?P<value>[^，。,\s]+)
            .*?
            (?:then|\u663e\u793a|\u8fd4\u56de)?\s*
            (?P<t>["'][^"']+["'])
            .*?
            (?:{_ZH_ELSE}|else)\s*
            (?:\u663e\u793a|\u8fd4\u56de)?\s*
            (?P<f>["'][^"']+["'])
            """,
            raw_text,
            flags=re.IGNORECASE | re.VERBOSE,
        )
        if match_if_else:
            t_val = quoted_literals[0] if len(quoted_literals) > 0 else self._clean_literal(match_if_else.group("t"))
            f_val = quoted_literals[1] if len(quoted_literals) > 1 else self._clean_literal(match_if_else.group("f"))
            return {
                "conditional_mapping": True,
                "condition_field_hint": self._clean_literal(match_if_else.group("field")),
                "condition_operator": "==",
                "condition_value": self._clean_literal(match_if_else.group("value")),
                "true_output": t_val,
                "false_output": f_val,
            }

        return {}

    @staticmethod
    def _extract_quoted_literals(text: str) -> List[str]:
        """Extract all quoted string literals from requirement text."""

        matches = re.findall(r"""["']([^"']+)["']""", text or "")
        return [item.strip() for item in matches if item.strip()]

    @staticmethod
    def _extract_field_hint_candidates(text: str) -> List[str]:
        """Extract rough field-hint candidates from dot-path and key phrases."""

        hints = [m.group(0) for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", text or "")]
        for probe in (_ZH_CUSTOMER_GENDER, "gender", "sex", _ZH_BILL_CYCLE, "regionId", "be_id"):
            if probe in text:
                hints.append(probe)
        return list(dict.fromkeys(hints))

    @staticmethod
    def _clean_literal(value: str) -> str:
        """Trim wrapping quotes and spaces from extracted literal value."""

        return (value or "").strip().strip("\"' ")

    @staticmethod
    def _contains_any(raw_text: str, normalized_text: str, probes: Sequence[str]) -> bool:
        """Return True when any probe appears in raw or normalized text."""

        return any(probe in raw_text or probe in normalized_text for probe in probes)

    @staticmethod
    def _extract_function_like_tokens(text: str) -> List[str]:
        """Extract tokens like `ClassName.MethodName` as function candidates."""

        pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
        return [match.group(0) for match in pattern.finditer(text or "")]

    @staticmethod
    def _dedup_source_types(source_types: Sequence[IntentSourceType]) -> List[IntentSourceType]:
        """Deduplicate source types while keeping first appearance order."""

        deduped: List[IntentSourceType] = []
        seen: set[IntentSourceType] = set()
        for source in source_types:
            if source not in seen:
                seen.add(source)
                deduped.append(source)
        return deduped

    @staticmethod
    def _dedup_operations(operations: Sequence[OperationIntent]) -> List[OperationIntent]:
        """Deduplicate operations by op_type while keeping first operation."""

        deduped: List[OperationIntent] = []
        seen: set[str] = set()
        for op in operations:
            if op.op_type not in seen:
                seen.add(op.op_type)
                deduped.append(op)
        return deduped
