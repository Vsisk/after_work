from __future__ import annotations

import json
import re
from pathlib import Path

from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.resource_retrieval.schemas import ExtractedConcepts
from billing_dsl_agent.resource_retrieval.text_normalizer import DEFAULT_TEXT_NORMALIZER, TextNormalizer

try:
    import jieba  # type: ignore
except Exception:  # pragma: no cover
    jieba = None


class ConceptExtractor:
    def __init__(
        self,
        domain_terms_path: str | Path | None = None,
        aliases_path: str | Path | None = None,
        text_normalizer: TextNormalizer | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parent
        self._domain_terms_path = Path(domain_terms_path or (base_dir / "domain_terms.txt"))
        self._aliases_path = Path(aliases_path or (base_dir / "aliases.json"))
        self._text_normalizer = text_normalizer or DEFAULT_TEXT_NORMALIZER
        self._domain_terms = self._load_domain_terms()
        self._aliases = self._load_aliases()
        if jieba is not None:
            for term in self._domain_terms:
                jieba.add_word(term)

    def extract(self, user_query: str, node_def: NodeDef) -> ExtractedConcepts:
        text_parts = [
            user_query or "",
            node_def.node_name or "",
            node_def.description or "",
            node_def.node_path or "",
        ]
        joined_text = " ".join(text_parts)
        base_tokens = self._tokenize(joined_text)
        identifier_tokens: list[str] = []
        for item in text_parts:
            for token in re.findall(r"[A-Za-z0-9_]+", item):
                identifier_tokens.extend(self._text_normalizer.split_identifier(token))

        domain_terms = [term for term in self._domain_terms if term and term.lower() in joined_text.lower()]
        keywords = self._dedupe([*base_tokens, *identifier_tokens, *domain_terms])
        noun_phrases = self._dedupe(
            [item for item in [node_def.node_name, node_def.description, *domain_terms] if item]
        )

        alias_hits: dict[str, list[str]] = {}
        token_set = set(keywords)
        for key, values in self._aliases.items():
            normalized_key = key.lower()
            normalized_values = [item.lower() for item in values if item]
            if normalized_key in token_set or any(item in token_set for item in normalized_values):
                alias_hits[key] = self._dedupe([key, *values])
                keywords = self._dedupe([*keywords, *alias_hits[key]])

        return ExtractedConcepts(
            keywords=keywords,
            noun_phrases=noun_phrases,
            domain_terms=self._dedupe(domain_terms),
            aliases=alias_hits,
        )

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        if jieba is not None:
            tokens.extend(str(item).strip().lower() for item in jieba.cut(text, cut_all=False))
        else:
            tokens.extend(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower()))
        expanded: list[str] = []
        for item in tokens:
            if not item:
                continue
            expanded.append(item)
            if re.fullmatch(r"[A-Za-z0-9_]+", item):
                expanded.extend(self._text_normalizer.split_identifier(item))
        return self._dedupe([item for item in expanded if item and not item.isspace()])

    def _load_domain_terms(self) -> list[str]:
        if not self._domain_terms_path.exists():
            return []
        return self._dedupe(
            [line.strip() for line in self._domain_terms_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        )

    def _load_aliases(self) -> dict[str, list[str]]:
        if not self._aliases_path.exists():
            return {}
        payload = json.loads(self._aliases_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        result: dict[str, list[str]] = {}
        for key, value in payload.items():
            if isinstance(value, list):
                result[str(key)] = [str(item) for item in value if str(item)]
        return result

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered
