"""Index helpers for resource lookup in matching/planning stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.context import ContextVarDef
from billing_dsl_agent.types.function import FunctionDef


@dataclass(slots=True)
class ContextIndex:
    """Fast lookup index for context variables and field-like paths."""

    by_name: Dict[str, ContextVarDef] = field(default_factory=dict)
    by_path: Dict[str, ContextVarDef] = field(default_factory=dict)


@dataclass(slots=True)
class BOIndex:
    """Fast lookup index for BO definitions."""

    by_name: Dict[str, BODef] = field(default_factory=dict)


@dataclass(slots=True)
class FunctionIndex:
    """Fast lookup index for function definitions."""

    by_full_name: Dict[str, FunctionDef] = field(default_factory=dict)
    by_method_name: Dict[str, List[FunctionDef]] = field(default_factory=dict)


def build_context_path_index(context_vars: Iterable[ContextVarDef]) -> ContextIndex:
    """Build context index by variable name and `var.field` path.

    Paths are flattened from `ContextVarDef.fields` only for MVP lookup needs.
    """

    by_name: Dict[str, ContextVarDef] = {}
    by_path: Dict[str, ContextVarDef] = {}
    for var in context_vars:
        by_name[var.name] = var
        by_path[var.name] = var
        for field_def in var.fields:
            by_path[f"{var.name}.{field_def.name}"] = var
    return ContextIndex(by_name=by_name, by_path=by_path)


def build_bo_index(bos: Iterable[BODef]) -> BOIndex:
    """Build BO lookup index by `bo.name`."""

    return BOIndex(by_name={bo.name: bo for bo in bos})


def build_function_index(functions: Iterable[FunctionDef]) -> FunctionIndex:
    """Build function index by full name and method name."""

    by_full_name: Dict[str, FunctionDef] = {}
    by_method_name: Dict[str, List[FunctionDef]] = {}
    for fn in functions:
        by_full_name[fn.full_name] = fn
        by_method_name.setdefault(fn.method_name, []).append(fn)
    return FunctionIndex(by_full_name=by_full_name, by_method_name=by_method_name)
