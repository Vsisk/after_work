from __future__ import annotations

from importlib import import_module

__all__ = [
    "DSLAgent",
    "LLMPlanner",
    "StubOpenAIClient",
    "GenerateDSLRequest",
    "GenerateDSLResponse",
    "NodeDef",
    "ResourceManager",
    "load_bo_registry_from_json",
    "load_bo_registry_from_file",
    "load_context_registry_from_json",
    "load_context_registry_from_file",
    "build_context_path_map",
    "ResourceLoader",
    "MockSemanticSelector",
    "OpenAISemanticSelector",
]

_EXPORT_MAP = {
    "DSLAgent": ("billing_dsl_agent.agent_entry", "DSLAgent"),
    "LLMPlanner": ("billing_dsl_agent.llm_planner", "LLMPlanner"),
    "StubOpenAIClient": ("billing_dsl_agent.llm_planner", "StubOpenAIClient"),
    "GenerateDSLRequest": ("billing_dsl_agent.models", "GenerateDSLRequest"),
    "GenerateDSLResponse": ("billing_dsl_agent.models", "GenerateDSLResponse"),
    "NodeDef": ("billing_dsl_agent.models", "NodeDef"),
    "ResourceManager": ("billing_dsl_agent.resource_manager", "ResourceManager"),
    "load_bo_registry_from_json": ("billing_dsl_agent.bo_loader", "load_bo_registry_from_json"),
    "load_bo_registry_from_file": ("billing_dsl_agent.bo_loader", "load_bo_registry_from_file"),
    "load_context_registry_from_json": ("billing_dsl_agent.context_loader", "load_context_registry_from_json"),
    "load_context_registry_from_file": ("billing_dsl_agent.context_loader", "load_context_registry_from_file"),
    "build_context_path_map": ("billing_dsl_agent.context_loader", "build_context_path_map"),
    "ResourceLoader": ("billing_dsl_agent.resource_loader", "ResourceLoader"),
    "MockSemanticSelector": ("billing_dsl_agent.semantic_selector", "MockSemanticSelector"),
    "OpenAISemanticSelector": ("billing_dsl_agent.semantic_selector", "OpenAISemanticSelector"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
