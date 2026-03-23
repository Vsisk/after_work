"""Request/response payloads for DSL generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .agent import PlanDraft
from .bo import BODef
from .common import GeneratedDSL, StructuredExplanation
from .context import ContextVarDef
from .dsl import DSLSpec, ValuePlan
from .function import FunctionDef
from .intent import NodeIntent
from .node import NodeDef
from .plan import ResolvedEnvironment, ResourceBinding
from .validation import ValidationResult


@dataclass(slots=True)
class GenerateDSLRequest:
    """Input payload to generate DSL for a target node."""

    user_requirement: str
    node_def: NodeDef
    global_context_vars: List[ContextVarDef] = field(default_factory=list)
    local_context_vars: List[ContextVarDef] = field(default_factory=list)
    available_bos: List[BODef] = field(default_factory=list)
    available_functions: List[FunctionDef] = field(default_factory=list)
    dsl_spec: Optional[DSLSpec] = None


@dataclass(slots=True)
class GenerateDSLResponse:
    """Output payload for DSL generation pipeline."""

    success: bool
    dsl_code: str = ""
    plan_draft: Optional[PlanDraft] = None
    generated_dsl: Optional[GeneratedDSL] = None
    intent: Optional[NodeIntent] = None
    resolved_environment: Optional[ResolvedEnvironment] = None
    resource_binding: Optional[ResourceBinding] = None
    value_plan: Optional[ValuePlan] = None
    explanation: Optional[StructuredExplanation] = None
    validation_result: Optional[ValidationResult] = None
    failure_reason: Optional[str] = None
