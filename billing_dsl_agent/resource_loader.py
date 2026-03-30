from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple

from billing_dsl_agent.bo_loader import load_bo_registry_from_json
from billing_dsl_agent.bo_models import BORegistry
from billing_dsl_agent.context_loader import load_context_registry_from_json
from billing_dsl_agent.context_models import ContextRegistry
from billing_dsl_agent.log_utils import get_logger
from billing_dsl_agent.resource_manager import ResourceManager

logger = get_logger(__name__)


@dataclass(slots=True)
class LoadedResources:
    context_registry: ContextRegistry
    bo_registry: BORegistry
    function_payload: Dict[str, Any]
    edsl_tree: Dict[str, Any]


class ResourceProvider(Protocol):
    def fetch(self, site_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        ...


@dataclass(slots=True)
class InMemoryResourceProvider:
    dataset: Dict[Tuple[str, str], Dict[str, Any]]

    def fetch(self, site_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        return self.dataset.get((site_id, project_id))


@dataclass(slots=True)
class ResourceLoader:
    provider: ResourceProvider

    def load(self, site_id: str, project_id: str) -> LoadedResources:
        logger.info("resource_loader_started site_id=%s project_id=%s", site_id, project_id)
        payload = self.provider.fetch(site_id, project_id) or {}
        logger.info(
            "resource_payload_fetched site_id=%s project_id=%s has_context=%s has_bo=%s has_function=%s has_edsl=%s",
            site_id,
            project_id,
            bool(payload.get("context")),
            bool(payload.get("bo")),
            bool(payload.get("function")),
            bool(payload.get("edsl")),
        )
        context_registry = load_context_registry_from_json(payload.get("context") or {})
        bo_registry = load_bo_registry_from_json(payload.get("bo") or {})
        function_payload = ResourceManager().normalize_functions(payload.get("function") or {})
        logger.info(
            "resource_loader_completed context_count=%s bo_sys_count=%s bo_custom_count=%s function_group_count=%s",
            len(getattr(context_registry, "nodes_by_id", {}) or {}),
            len(getattr(bo_registry, "system_bos", []) or []),
            len(getattr(bo_registry, "custom_bos", []) or []),
            len(function_payload),
        )
        return LoadedResources(
            context_registry=context_registry,
            bo_registry=bo_registry,
            function_payload=function_payload,
            edsl_tree=payload.get("edsl") or {},
        )
