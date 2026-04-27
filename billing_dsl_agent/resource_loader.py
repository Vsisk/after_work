from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, Tuple

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


@dataclass(slots=True)
class ResourceCacheEntry:
    payload_signature: str
    raw_payload: Dict[str, Any]
    loaded: LoadedResources


class ResourceLoader:
    _instance: "ResourceLoader | None" = None
    _instance_lock = RLock()

    def __new__(cls) -> "ResourceLoader":
        with cls._instance_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._cache = {}
                instance._cache_lock = RLock()
                instance._resource_dataset = None
                cls._instance = instance
            return cls._instance

    def __init__(self) -> None:
        pass

    @classmethod
    def get_instance(cls) -> "ResourceLoader":
        return cls()

    def set_resource_dataset(self, dataset: Dict[Tuple[str, str], Dict[str, Any]], *, clear_cache: bool = True) -> "ResourceLoader":
        with self._cache_lock:
            self._resource_dataset = dataset
            if clear_cache:
                self._cache.clear()
        return self

    def clear_cache(self, site_id: str | None = None, project_id: str | None = None) -> None:
        with self._cache_lock:
            if site_id is None and project_id is None:
                self._cache.clear()
                return
            self._cache.pop(self._build_resource_key(site_id or "", project_id or ""), None)

    def is_cached(self, site_id: str, project_id: str) -> bool:
        with self._cache_lock:
            return self._build_resource_key(site_id, project_id) in self._cache

    def load(self, site_id: str, project_id: str) -> LoadedResources:
        resource_key = self._build_resource_key(site_id, project_id)
        logger.info("resource_loader_refresh_started site_id=%s project_id=%s", site_id, project_id)
        payload = self._fetch_latest_payload(site_id, project_id)
        signature = self._payload_signature(payload)

        with self._cache_lock:
            cached = self._cache.get(resource_key)
            if cached is not None and cached.payload_signature == signature:
                logger.info("resource_loader_cache_hit site_id=%s project_id=%s", site_id, project_id)
                return cached.loaded

        if cached is None:
            logger.info("resource_loader_cache_miss site_id=%s project_id=%s", site_id, project_id)
        else:
            logger.info("resource_loader_cache_changed site_id=%s project_id=%s", site_id, project_id)

        loaded = self._build_loaded_resources(payload)
        entry = ResourceCacheEntry(
            payload_signature=signature,
            raw_payload=copy.deepcopy(payload),
            loaded=loaded,
        )
        with self._cache_lock:
            self._cache[resource_key] = entry
        return loaded

    def get_resource(self, site_id: str, project_id: str, edsl_tree: Dict[str, Any] | None = None) -> LoadedResources:
        if edsl_tree is None:
            return self.load(site_id, project_id)
        payload = self._fetch_latest_payload(site_id, project_id)
        payload["edsl"] = edsl_tree
        return self._build_loaded_resources(payload)

    def _fetch_latest_payload(self, site_id: str, project_id: str) -> Dict[str, Any]:
        if self._resource_dataset is not None:
            payload = self._resource_dataset.get((site_id, project_id), {})
        else:
            payload = self._get_resource_from_file(site_id, project_id)
        if not isinstance(payload, dict):
            logger.warning("resource_payload_invalid site_id=%s project_id=%s payload_type=%s", site_id, project_id, type(payload).__name__)
            return {}
        return copy.deepcopy(payload)

    def _build_loaded_resources(self, payload: Dict[str, Any]) -> LoadedResources:
        logger.info(
            "resource_payload_fetched has_context=%s has_bo=%s has_function=%s has_edsl=%s",
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

    def _payload_signature(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)

    def _build_resource_key(self, site_id: str, project_id: str) -> str:
        return f"{site_id or ''}:{project_id or ''}"

    def _get_resource_from_file(self, site_id: str, project_id: str) -> Dict[str, Any]:
        return {
            "context": self._load_context(site_id, project_id),
            "bo": self._load_bo(site_id, project_id),
            "function": self._load_function(site_id, project_id),
            "edsl": self._load_edsl(site_id, project_id),
        }

    def _load_context(self, site_id: str, project_id: str) -> Dict[str, Any]:
        return {}

    def _load_bo(self, site_id: str, project_id: str) -> Dict[str, Any]:
        return {}

    def _load_function(self, site_id: str, project_id: str) -> Dict[str, Any]:
        return {}

    def _load_edsl(self, site_id: str, project_id: str) -> Dict[str, Any]:
        return {}
