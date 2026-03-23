"""Rule-based requirement parser for MVP usage."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from billing_dsl_agent.types.intent import IntentSourceType, NodeIntent, OperationIntent
from billing_dsl_agent.types.node import NodeDef

_ZH_CURRENT = "\u5f53\u524d"
_ZH_GLOBAL_CONTEXT = "\u5168\u5c40\u4e0a\u4e0b\u6587"
_ZH_LOCAL_CONTEXT = "\u5c40\u90e8\u4e0a\u4e0b\u6587"
_ZH_LOCAL_VAR = "\u5c40\u90e8\u53d8\u91cf"
_ZH_QUERY = "\u67e5\u8be2"
_ZH_LOOKUP = "\u67e5\u8868"
_ZH_FIRST = "\u7b2c\u4e00\u6761"
_ZH_RETURN = "\u8fd4\u56de"
_ZH_SHOW = "\u663e\u793a"
_ZH_IF = "\u5982\u679c"
_ZH_ELSE = "\u5426\u5219"
_ZH_WHEN = "\u5f53"
_ZH_FORMAT = "\u683c\u5f0f\u5316"
_ZH_TWO_DECIMAL = "\u4e24\u4f4d\u5c0f\u6570"
_ZH_USE = "\u4f7f\u7528"
_ZH_TAKE = "\u53d6"
_ZH_CUSTOMER_NAME = "\u5ba2\u6237\u540d\u79f0"
_ZH_CUSTOMER_GENDER = "\u5ba2\u6237\u6027\u522b"
_ZH_BILL_CYCLE = "\u8d26\u671f"


class SimpleRequirementParser:
    """Parse requirement text into NodeIntent with lightweight keyword rules."""

    _CONTEXT_KEYWORDS: Sequence[str] = ("$ctx$", "ctx", "context", _ZH_CURRENT, _ZH_GLOBAL_CONTEXT, _ZH_USE, _ZH_TAKE)
    _LOCAL_CONTEXT_KEYWORDS: Sequence[str] = ("$local$", "local", _ZH_LOCAL_CONTEXT, _ZH_LOCAL_VAR)
    _BO_QUERY_KEYWORDS: Sequence[str] = ("select", "select_one", _ZH_QUERY, _ZH_LOOKUP)
    _NAMING_SQL_KEYWORDS: Sequence[str] = ("fetch", "fetch_one", "naming sql", "namingsql")
    _FUNCTION_KEYWORDS: Sequence[str] = ("format", _ZH_FORMAT, "exists", "concat", "Common.")
    _CONDITIONAL_KEYWORDS: Sequence[str] = ("if", _ZH_IF, _ZH_ELSE, _ZH_WHEN)
    _EXPRESSION_KEYWORDS: Sequence[str] = ("expression", _ZH_FORMAT, "concat", "\u62fc\u63a5", "\u8ba1\u7b97")

    def parse(self, user_requirement: str, node_def: NodeDef) -> NodeIntent:
        """Parse text requirement into a stable NodeIntent using simple rules."""

        raw_text = (user_requirement or "").strip()
        normalized_text = self._normalize_requirement_text(raw_text)
        semantic_slots = self._detect_semantic_slots(raw_text, normalized_text)
        source_types = self._detect_source_types(raw_text, normalized_text, semantic_slots)
        operations = self._detect_operations(raw_text, normalized_text, source_types, semantic_slots)
        constraints = self._detect_constraints(raw_text, normalized_text)

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
        """Lowercase and normalize punctuation/whitespace for matching."""

        normalized = (text or "").strip().lower()
        normalized = normalized.replace("\uff0c", ",").replace("\uff1a", ":").replace("\u3002", ".")
        normalized = normalized.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
        return " ".join(normalized.split())

    def _detect_semantic_slots(self, raw_text: str, normalized_text: str) -> Dict[str, Any]:
        """Extract semantic slots that can feed resource binding and planning."""

        slots: Dict[str, Any] = {}

        context_hints = self._extract_context_hints(raw_text)
        if context_hints:
            slots["context_field_hints"] = context_hints

        query_hints = self._extract_query_hints(raw_text, normalized_text)
        if query_hints:
            slots.update(query_hints)

        function_hints = self._extract_function_hints(raw_text, normalized_text)
        if function_hints:
            slots.update(function_hints)

        conditional_mapping = self._extract_conditional_mapping(raw_text, normalized_text)
        if conditional_mapping:
            slots.update(conditional_mapping)
        else:
            conditional = self._extract_conditional_hints(raw_text, normalized_text)
            if conditional:
                slots.update(conditional)

        return slots

    def _detect_source_types(
        self,
        raw_text: str,
        normalized_text: str,
        semantic_slots: Dict[str, Any],
    ) -> List[IntentSourceType]:
        """Infer source categories from rule matches and extracted slots."""

        source_types: List[IntentSourceType] = []

        context_hints = semantic_slots.get("context_field_hints") or []
        if context_hints or self._contains_any(raw_text, normalized_text, self._CONTEXT_KEYWORDS):
            source_types.append(IntentSourceType.CONTEXT)

        if semantic_slots.get("uses_local_context") or self._contains_any(raw_text, normalized_text, self._LOCAL_CONTEXT_KEYWORDS):
            source_types.append(IntentSourceType.LOCAL_CONTEXT)

        if semantic_slots.get("bo_name") or self._contains_any(raw_text, normalized_text, self._BO_QUERY_KEYWORDS):
            source_types.append(IntentSourceType.BO_QUERY)

        if semantic_slots.get("naming_sql_name") or self._contains_any(raw_text, normalized_text, self._NAMING_SQL_KEYWORDS):
            source_types.append(IntentSourceType.NAMING_SQL)

        if semantic_slots.get("function_name") or self._contains_any(raw_text, normalized_text, self._FUNCTION_KEYWORDS):
            source_types.append(IntentSourceType.FUNCTION)

        if (
            semantic_slots.get("conditional_mapping")
            or semantic_slots.get("condition_field_hint")
            or self._contains_any(raw_text, normalized_text, self._CONDITIONAL_KEYWORDS)
        ):
            source_types.append(IntentSourceType.CONDITIONAL)

        if semantic_slots.get("function_name") or semantic_slots.get("target_field") or self._contains_any(
            raw_text, normalized_text, self._EXPRESSION_KEYWORDS
        ):
            source_types.append(IntentSourceType.EXPRESSION)

        return self._dedup_source_types(source_types)

    def _detect_operations(
        self,
        raw_text: str,
        normalized_text: str,
        source_types: Sequence[IntentSourceType],
        semantic_slots: Dict[str, Any],
    ) -> List[OperationIntent]:
        """Build deduped operation intents from detected categories and slots."""

        del raw_text
        operations: List[OperationIntent] = []

        if IntentSourceType.CONTEXT in source_types:
            operations.append(
                OperationIntent(
                    op_type="read_context",
                    description="Read value from context.",
                    expected_inputs=list(semantic_slots.get("context_field_hints") or ["context_path_or_name"]),
                )
            )

        if IntentSourceType.LOCAL_CONTEXT in source_types:
            operations.append(
                OperationIntent(
                    op_type="read_local_context",
                    description="Read value from local context.",
                    expected_inputs=list(semantic_slots.get("context_field_hints") or ["local_context_path_or_name"]),
                )
            )

        if IntentSourceType.BO_QUERY in source_types:
            op_type = "query_bo"
            if semantic_slots.get("query_mode") == "select_one" or "select_one" in normalized_text:
                op_type = "query_bo_select_one"
            elif semantic_slots.get("query_mode") == "select":
                op_type = "query_bo_select"
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description="Query BO resources.",
                    expected_inputs=[
                        semantic_slots.get("bo_name", "bo_name"),
                        semantic_slots.get("target_field", "target_field"),
                    ],
                )
            )

        if IntentSourceType.NAMING_SQL in source_types:
            op_type = "query_naming_sql_fetch_one" if semantic_slots.get("query_mode") == "fetch_one" else "query_naming_sql"
            operations.append(
                OperationIntent(
                    op_type=op_type,
                    description="Query naming sql resources.",
                    expected_inputs=[semantic_slots.get("naming_sql_name", "naming_sql_name")],
                )
            )

        if IntentSourceType.FUNCTION in source_types:
            expected_inputs: List[str] = []
            function_name = semantic_slots.get("function_name")
            if function_name:
                expected_inputs.append(str(function_name))
            expected_inputs.extend(str(item) for item in (semantic_slots.get("function_args_hint") or []))
            operations.append(
                OperationIntent(
                    op_type="call_function",
                    description="Call function candidate from requirement text.",
                    expected_inputs=expected_inputs or ["function_name"],
                )
            )

        if IntentSourceType.CONDITIONAL in source_types:
            cond_op_type = "build_conditional_mapping" if semantic_slots.get("conditional_mapping") else "build_conditional"
            operations.append(
                OperationIntent(
                    op_type=cond_op_type,
                    description="Build conditional expression.",
                    expected_inputs=[
                        str(semantic_slots.get("condition_field_hint", "condition")),
                        str(semantic_slots.get("true_output", "true_expr")),
                        str(semantic_slots.get("false_output", "false_expr")),
                    ],
                )
            )

        if IntentSourceType.EXPRESSION in source_types:
            operations.append(
                OperationIntent(
                    op_type="build_expression",
                    description="Build expression from requirement.",
                    expected_inputs=[
                        str(semantic_slots.get("target_field", semantic_slots.get("function_name", "expression_parts")))
                    ],
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
        """Extract a few stable constraints from requirement text."""

        constraints: List[str] = []
        if "\u4e0d\u80fd\u4e3a\u7a7a" in raw_text or "not null" in normalized_text:
            constraints.append("result_must_not_be_null")
        if "\u9ed8\u8ba4" in raw_text or "default" in normalized_text:
            constraints.append("should_have_default_fallback")
        return constraints

    def _extract_context_hints(self, raw_text: str) -> List[str]:
        """Extract context-like field hints from direct value-reading requirements."""

        hints: List[str] = []

        for match in re.finditer(r"\$ctx\$\.(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)", raw_text):
            hints.append(match.group(1))

        for match in re.finditer(r"\$local\$\.(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)", raw_text):
            hints.append(match.group(1))

        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", raw_text):
            token = match.group(1)
            if token.lower() in {"select", "select_one", "fetch", "fetch_one", "if", "else", "when"}:
                continue
            hints.append(token)

        zh_aliases = {
            _ZH_CUSTOMER_NAME: "name",
            _ZH_CUSTOMER_GENDER: "gender",
            _ZH_BILL_CYCLE: "billCycleId",
            "\u91d1\u989d": "amount",
        }
        for label, mapped in zh_aliases.items():
            if label in raw_text:
                hints.append(mapped)

        if any(probe in raw_text for probe in (_ZH_LOCAL_VAR, _ZH_LOCAL_CONTEXT, "$local$", "local")):
            hints.append("local")

        return self._dedup_strings(hints)

    def _extract_query_hints(self, raw_text: str, normalized_text: str) -> Dict[str, Any]:
        """Extract BO query related slots."""

        slots: Dict[str, Any] = {}

        query_mode = ""
        if "select_one" in normalized_text or _ZH_FIRST in raw_text or "\u7b2c\u4e00\u6761\u8bb0\u5f55" in raw_text:
            query_mode = "select_one"
        elif "select" in normalized_text or _ZH_QUERY in raw_text or _ZH_LOOKUP in raw_text:
            query_mode = "select"
        elif "fetch_one" in normalized_text:
            query_mode = "fetch_one"
        elif "fetch" in normalized_text:
            query_mode = "fetch"
        if query_mode:
            slots["query_mode"] = query_mode

        bo_match = re.search(
            r"(?:query|select(?:_one)?|fetch(?:_one)?|\u67e5\u8be2|\u67e5\u8868)\s+([A-Za-z_][A-Za-z0-9_]*)",
            raw_text,
            flags=re.IGNORECASE,
        )
        if bo_match:
            slots["bo_name"] = bo_match.group(1)
        else:
            zh_bo_match = re.search(rf"{_ZH_QUERY}\s*([A-Za-z_][A-Za-z0-9_]*)", raw_text)
            if zh_bo_match:
                slots["bo_name"] = zh_bo_match.group(1)

        field_match = re.search(
            r"(?:\u53d6|\u8fd4\u56de|field)\s*(?:\u7b2c\u4e00\u6761\u8bb0\u5f55\u7684)?\s*([A-Za-z_][A-Za-z0-9_]*)",
            raw_text,
            flags=re.IGNORECASE,
        )
        if field_match:
            slots["target_field"] = field_match.group(1)

        if "target_field" not in slots:
            after_match = re.search(r"\u540e\u53d6\u5b57\u6bb5\s*([A-Za-z_][A-Za-z0-9_]*)", raw_text)
            if after_match:
                slots["target_field"] = after_match.group(1)

        if slots.get("bo_name"):
            context_hints = self._extract_context_hints(raw_text)
            if context_hints:
                slots["context_field_hints"] = context_hints

        return slots

    def _extract_function_hints(self, raw_text: str, normalized_text: str) -> Dict[str, Any]:
        """Extract function call candidates and argument hints."""

        slots: Dict[str, Any] = {}

        full_name_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b", raw_text)
        if full_name_match:
            slots["function_name"] = full_name_match.group(1)
            args = list(self._extract_context_hints(raw_text))
            if args:
                slots["function_args_hint"] = args
            return slots

        if _ZH_FORMAT in raw_text or "format" in normalized_text:
            slots["function_name"] = "format_decimal"
            args: List[Any] = []
            context_hints = self._extract_context_hints(raw_text)
            if context_hints:
                args.extend(context_hints)
            if _ZH_TWO_DECIMAL in raw_text or "two decimal" in normalized_text or "2\u4f4d\u5c0f\u6570" in raw_text:
                args.append(2)
                slots["format_precision"] = 2
            slots["function_args_hint"] = args or ["value"]

        return slots

    def _extract_conditional_hints(self, raw_text: str, normalized_text: str) -> Dict[str, Any]:
        """Extract simple if/else conditional slots."""

        del normalized_text
        quoted_literals = self._extract_quoted_literals(raw_text)
        pattern = re.search(
            rf"(?:{_ZH_IF}|if)\s*(?P<field>[^=,:\s\u5219]+?)\s*(?:\u4e3a|=|==)\s*(?P<value>[^,\s\u5219]+)\s*(?:\u5219)?"
            rf".*?(?:{_ZH_RETURN}|{_ZH_SHOW})?\s*(?P<true>[A-Za-z0-9_.\"']+)"
            rf".*?(?:{_ZH_ELSE}|else)\s*(?:{_ZH_RETURN}|{_ZH_SHOW})?\s*(?P<false>[A-Za-z0-9_.\"']+)",
            raw_text,
            flags=re.IGNORECASE,
        )
        if not pattern:
            return {}

        true_output = quoted_literals[0] if quoted_literals else self._clean_literal(pattern.group("true"))
        false_output = quoted_literals[1] if len(quoted_literals) > 1 else self._clean_literal(pattern.group("false"))

        return {
            "condition_field_hint": self._normalize_field_hint(pattern.group("field")),
            "condition_operator": "==",
            "condition_value": self._clean_literal(pattern.group("value")),
            "true_output": true_output,
            "false_output": false_output,
        }

    def _extract_conditional_mapping(self, raw_text: str, normalized_text: str) -> Dict[str, Any]:
        """Extract conditional mapping slots from when/if mapping statements."""

        del normalized_text
        quoted_literals = self._extract_quoted_literals(raw_text)
        case_matches = list(
            re.finditer(
                rf"{_ZH_WHEN}\s*(?P<field>[^,\u65f6\u4e3a]+?)\s*\u4e3a\s*(?P<value>[^,\u65f6\s]+)\s*\u65f6",
                raw_text,
            )
        )
        if len(case_matches) < 2 or len(quoted_literals) < 2:
            return {}

        first_case = case_matches[0]
        second_case = case_matches[1]
        true_output = quoted_literals[0]
        false_output = quoted_literals[1]

        return {
            "conditional_mapping": True,
            "condition_field_hint": self._normalize_field_hint(first_case.group("field")),
            "condition_operator": "==",
            "condition_value": self._clean_literal(first_case.group("value")),
            "true_output": true_output,
            "false_output": false_output,
            "conditional_cases": [
                {
                    "when": {
                        "field_hint": self._normalize_field_hint(first_case.group("field")),
                        "operator": "==",
                        "value": self._clean_literal(first_case.group("value")),
                    },
                    "then": true_output,
                },
                {
                    "when": {
                        "field_hint": self._normalize_field_hint(second_case.group("field")),
                        "operator": "==",
                        "value": self._clean_literal(second_case.group("value")),
                    },
                    "then": false_output,
                },
            ],
        }

    @staticmethod
    def _extract_quoted_literals(text: str) -> List[str]:
        """Extract quoted string literals."""

        return [item.strip() for item in re.findall(r"""["']([^"']+)["']""", text or "") if item.strip()]

    @staticmethod
    def _normalize_field_hint(value: str) -> str:
        cleaned = (value or "").strip()
        if cleaned == _ZH_CUSTOMER_NAME:
            return _ZH_CUSTOMER_NAME
        if cleaned == _ZH_CUSTOMER_GENDER:
            return _ZH_CUSTOMER_GENDER
        if cleaned == _ZH_BILL_CYCLE:
            return _ZH_BILL_CYCLE
        return cleaned

    @staticmethod
    def _clean_literal(value: str) -> str:
        """Trim wrapping quotes and spaces from extracted literal value."""

        return (value or "").strip().strip("\"' ")

    @staticmethod
    def _contains_any(raw_text: str, normalized_text: str, probes: Sequence[str]) -> bool:
        """Return True when any probe appears in raw or normalized text."""

        return any(probe in raw_text or probe.lower() in normalized_text for probe in probes)

    @staticmethod
    def _dedup_source_types(source_types: Sequence[IntentSourceType]) -> List[IntentSourceType]:
        """Deduplicate source types while preserving order."""

        deduped: List[IntentSourceType] = []
        seen: set[IntentSourceType] = set()
        for source in source_types:
            if source not in seen:
                seen.add(source)
                deduped.append(source)
        return deduped

    @staticmethod
    def _dedup_operations(operations: Sequence[OperationIntent]) -> List[OperationIntent]:
        """Deduplicate operations by op_type while preserving order."""

        deduped: List[OperationIntent] = []
        seen: set[str] = set()
        for op in operations:
            if op.op_type not in seen:
                seen.add(op.op_type)
                deduped.append(op)
        return deduped

    @staticmethod
    def _dedup_strings(values: Sequence[Any]) -> List[str]:
        """Deduplicate string-like values while preserving order."""

        deduped: List[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value).strip()
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
