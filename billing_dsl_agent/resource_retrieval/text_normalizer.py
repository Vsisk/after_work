from __future__ import annotations

import re


class TextNormalizer:
    _CAMEL_PATTERN_1 = re.compile(r"([a-z0-9])([A-Z])")
    _CAMEL_PATTERN_2 = re.compile(r"([A-Z]+)([A-Z][a-z])")
    _ALNUM_PATTERN_1 = re.compile(r"([A-Za-z])([0-9])")
    _ALNUM_PATTERN_2 = re.compile(r"([0-9])([A-Za-z])")
    _SPACE_PATTERN = re.compile(r"\s+")
    _TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")

    def split_identifier(self, value: str) -> list[str]:
        if not value:
            return []
        expanded = value.replace("_", " ")
        expanded = self._CAMEL_PATTERN_2.sub(r"\1 \2", expanded)
        expanded = self._CAMEL_PATTERN_1.sub(r"\1 \2", expanded)
        expanded = self._ALNUM_PATTERN_1.sub(r"\1 \2", expanded)
        expanded = self._ALNUM_PATTERN_2.sub(r"\1 \2", expanded)
        expanded = self._SPACE_PATTERN.sub(" ", expanded).strip().lower()
        return [item for item in expanded.split(" ") if item]

    def expand_text(self, value: str) -> str:
        if not value:
            return ""
        ordered: list[str] = []
        for token in self._TOKEN_PATTERN.findall(value):
            token_lower = token.lower()
            if not ordered or ordered[-1] != token_lower:
                ordered.append(token_lower)
            if re.fullmatch(r"[A-Za-z0-9_]+", token):
                for part in self.split_identifier(token):
                    if not ordered or ordered[-1] != part:
                        ordered.append(part)
        return self._SPACE_PATTERN.sub(" ", " ".join(ordered)).strip()

    def normalize_text(self, value: str) -> str:
        return self._SPACE_PATTERN.sub(" ", self.expand_text(value)).strip()

    def tokenize(self, value: str) -> list[str]:
        tokens: list[str] = []
        for item in self.normalize_text(value).split(" "):
            if not item:
                continue
            tokens.append(item)
            if re.fullmatch(r"[\u4e00-\u9fff]+", item) and len(item) >= 2:
                for index in range(len(item) - 1):
                    tokens.append(item[index : index + 2])
        return tokens


DEFAULT_TEXT_NORMALIZER = TextNormalizer()
