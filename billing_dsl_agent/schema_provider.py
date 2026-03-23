from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from billing_dsl_agent.bo_loader import load_bo_registry_from_json
from billing_dsl_agent.bo_models import BORegistry
from billing_dsl_agent.context_loader import load_context_registry_from_json
from billing_dsl_agent.context_models import ContextRegistry
from billing_dsl_agent.resource_manager import ResourceManager


@dataclass(slots=True)
class FunctionRegistry:
    functions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class LoadedSchemas:
    bo_registry: BORegistry
    context_registry: ContextRegistry
    function_registry: FunctionRegistry


class SchemaProvider:
    """Load schemas by site/project dimensions.

    NOTE: loaders are in-memory placeholders for now and can be replaced by
    database/service readers in production.
    """

    def __init__(self) -> None:
        self.resource_manager = ResourceManager()

    def load_bos(self, site_id: str, project_id: str) -> BORegistry:
        payload = self._load_raw_bo_payload(site_id=site_id, project_id=project_id)
        return load_bo_registry_from_json(payload)

    def load_context(self, site_id: str, project_id: str) -> ContextRegistry:
        payload = self._load_raw_context_payload(site_id=site_id, project_id=project_id)
        return load_context_registry_from_json(payload)

    def load_functions(self, site_id: str, project_id: str) -> FunctionRegistry:
        payload = self._load_raw_function_payload(site_id=site_id, project_id=project_id)
        normalized = self.resource_manager.normalize_functions(payload)
        return FunctionRegistry(functions=list(normalized.get("functions") or []))

    def load_all(self, site_id: str, project_id: str) -> LoadedSchemas:
        return LoadedSchemas(
            bo_registry=self.load_bos(site_id=site_id, project_id=project_id),
            context_registry=self.load_context(site_id=site_id, project_id=project_id),
            function_registry=self.load_functions(site_id=site_id, project_id=project_id),
        )

    def _load_raw_bo_payload(self, site_id: str, project_id: str) -> Dict[str, Any]:
        _ = (site_id, project_id)
        return {
            "sys_bo_list": [
                {
                    "bo_name": "CustomerBO",
                    "bo_desc": "客户对象",
                    "property_list": [
                        {
                            "field_name": "id",
                            "description": "客户ID",
                            "is_list": False,
                            "data_type": "key",
                            "data_type_name": "string",
                        },
                        {
                            "field_name": "name",
                            "description": "客户名称",
                            "is_list": False,
                            "data_type": "basic",
                            "data_type_name": "string",
                        },
                        {
                            "field_name": "gender",
                            "description": "客户性别",
                            "is_list": False,
                            "data_type": "basic",
                            "data_type_name": "string",
                        },
                    ],
                    "or_mapping_list": [
                        {
                            "or_mapping_id": "customer_mapping_001",
                            "naming_sql_list": [
                                {
                                    "naming_sql_id": "get_customer_by_id",
                                    "sql_name": "getCustomerById",
                                    "param_list": [
                                        {
                                            "param_name": "customer_id",
                                            "is_list": False,
                                            "data_type": "basic",
                                            "data_type_name": "string",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "custom_bo_list": [],
        }

    def _load_raw_context_payload(self, site_id: str, project_id: str) -> Dict[str, Any]:
        _ = (site_id, project_id)
        return {
            "version": "1.0.0",
            "global_context": {
                "property_id": "gc_root",
                "property_name": "root",
                "value_source_type": "sub_property_wise",
                "sub_properties": [
                    {
                        "property_id": "gc_customer",
                        "property_name": "customer",
                        "annotation": "客户上下文",
                        "value_source_type": "sub_property_wise",
                        "return_type": {"is_list": False, "data_type": "bo", "data_type_name": "Customer"},
                        "sub_properties": [
                            {
                                "property_id": "gc_customer_id",
                                "property_name": "id",
                                "annotation": "客户ID",
                                "value_source_type": "cdsl",
                                "cdsl": "CurrentCustomer.id()",
                                "return_type": {"is_list": False, "data_type": "basic", "data_type_name": "string"},
                            },
                            {
                                "property_id": "gc_customer_gender",
                                "property_name": "gender",
                                "annotation": "客户性别",
                                "value_source_type": "cdsl",
                                "cdsl": "CurrentCustomer.gender()",
                                "return_type": {"is_list": False, "data_type": "basic", "data_type_name": "string"},
                            },
                        ],
                    },
                    {
                        "property_id": "gc_site",
                        "property_name": "site",
                        "annotation": "局点信息",
                        "value_source_type": "sub_property_wise",
                        "return_type": {"is_list": False, "data_type": "bo", "data_type_name": "Site"},
                        "sub_properties": [
                            {
                                "property_id": "gc_site_id",
                                "property_name": "id",
                                "annotation": "局点ID",
                                "value_source_type": "cdsl",
                                "cdsl": "CurrentSite.id()",
                                "return_type": {"is_list": False, "data_type": "basic", "data_type_name": "string"},
                            }
                        ],
                    },
                ],
            },
        }

    def _load_raw_function_payload(self, site_id: str, project_id: str) -> Dict[str, Any]:
        _ = (site_id, project_id)
        return {
            "version": "1.0.0",
            "native_func": [
                {
                    "class_name": "str",
                    "class_desc": "字符串函数",
                    "func_list": [
                        {
                            "func_id": "upper",
                            "func_name": "upper",
                            "func_desc": "转大写",
                            "func_scope": "global",
                            "param_list": [
                                {
                                    "param_name": "value",
                                    "is_list": False,
                                    "data_type": "basic",
                                    "data_type_name": "string",
                                }
                            ],
                        }
                    ],
                }
            ],
            "func": [
                {
                    "class_name": "Customer",
                    "class_desc": "客户函数",
                    "func_list": [
                        {
                            "func_name": "getSalutation",
                            "func_desc": "根据性别返回称谓",
                            "func_scope": "custom",
                            "param_list": [
                                {
                                    "param_name": "gender",
                                    "is_list": False,
                                    "data_type": "basic",
                                    "data_type_name": "string",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
