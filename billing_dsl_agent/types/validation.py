"""Validation result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ValidationErrorCode(str, Enum):
    """Known validation error codes."""

    FINAL_EXPRESSION_MISSING = "FINAL_EXPRESSION_MISSING"
    DUPLICATE_METHOD_NAME = "DUPLICATE_METHOD_NAME"
    UNKNOWN_METHOD_REF = "UNKNOWN_METHOD_REF"
    METHOD_REF_CYCLE = "METHOD_REF_CYCLE"
    UNKNOWN_CONTEXT_VAR = "UNKNOWN_CONTEXT_VAR"
    UNKNOWN_LOCAL_VAR = "UNKNOWN_LOCAL_VAR"
    UNKNOWN_BO = "UNKNOWN_BO"
    UNKNOWN_BO_FIELD = "UNKNOWN_BO_FIELD"
    UNKNOWN_NAMING_SQL = "UNKNOWN_NAMING_SQL"
    UNKNOWN_FUNCTION = "UNKNOWN_FUNCTION"
    FUNCTION_IMPORT_MISSING = "FUNCTION_IMPORT_MISSING"
    INVALID_QUERY_MODE = "INVALID_QUERY_MODE"
    UNSATISFIED_RESOURCE = "UNSATISFIED_RESOURCE"


@dataclass(slots=True)
class ValidationIssue:
    """Single validation issue entry."""

    code: ValidationErrorCode
    message: str
    location: Optional[str] = None
    level: str = "error"


@dataclass(slots=True)
class ValidationResult:
    """Validation summary over generated DSL."""

    syntax_valid: bool
    semantic_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.syntax_valid and self.semantic_valid
