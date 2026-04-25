from __future__ import annotations

from billing_dsl_agent.models import BOResource, ContextResource, FunctionResource
from billing_dsl_agent.resource_retrieval.schemas import ResourceDocument
from billing_dsl_agent.resource_retrieval.text_normalizer import DEFAULT_TEXT_NORMALIZER, TextNormalizer


class ResourceDocumentBuilder:
    def __init__(self, text_normalizer: TextNormalizer | None = None) -> None:
        self._text_normalizer = text_normalizer or DEFAULT_TEXT_NORMALIZER

    def build_context_documents(self, contexts: list[ContextResource]) -> list[ResourceDocument]:
        return [self.build_context_document(item) for item in contexts]

    def build_bo_documents(self, bos: list[BOResource]) -> list[ResourceDocument]:
        return [self.build_bo_document(item) for item in bos]

    def build_function_documents(self, functions: list[FunctionResource]) -> list[ResourceDocument]:
        return [self.build_function_document(item) for item in functions]

    def build_context_document(self, resource: ContextResource) -> ResourceDocument:
        name = self._value(resource, "name", "context_name", "id")
        path = self._value(resource, "path", "context_path", "full_path")
        description = self._value(resource, "description", "desc", default="")
        domain = self._value(resource, "domain", default="default")
        tags = self._list_value(resource, "tags")
        search_text = self._join_parts(
            [
                name,
                path,
                description,
                domain,
                " ".join(tags),
            ]
        )
        return ResourceDocument(
            resource_id=self._value(resource, "resource_id", "id", default=f"context:{path or name}"),
            resource_type="context",
            name=name,
            description=description,
            search_text=search_text,
            path=path,
            domain=domain,
            tags=tags,
            raw_ref=resource,
        )

    def build_bo_document(self, resource: BOResource) -> ResourceDocument:
        bo_name = self._value(resource, "bo_name", "name", "id")
        description = self._value(resource, "description", "bo_desc", "desc", default="")
        field_ids = [str(item) for item in self._list_value(resource, "field_ids", "fields")]
        if not field_ids:
            field_ids = [
                self._value(item, "field_name", "name", "id", default="")
                for item in self._list_value(resource, "property_list")
            ]
            field_ids = [item for item in field_ids if item]
        naming_sql_ids = [str(item) for item in self._list_value(resource, "naming_sql_ids")]
        naming_sqls = self._list_value(resource, "naming_sqls")
        if not naming_sqls:
            naming_sqls = []
            for mapping in self._list_value(resource, "or_mapping_list"):
                naming_sqls.extend(self._list_value(mapping, "naming_sql_list"))
        naming_sql_summaries = []
        for item in naming_sqls:
            params = " ".join(
                self._value(param, "param_name", "name", "id", default="")
                for param in self._list_value(item, "params", "param_list")
            )
            extra_fields = []
            raw_payload = self._value(item, "raw_payload", default={}) or {}
            if isinstance(raw_payload, dict):
                for key in ("return_fields", "fields", "annotation", "desc", "description"):
                    raw_value = raw_payload.get(key)
                    if isinstance(raw_value, list):
                        extra_fields.extend(str(entry) for entry in raw_value if entry)
                    elif isinstance(raw_value, str):
                        extra_fields.append(raw_value)
            naming_sql_summaries.append(
                " ".join(
                    [
                        self._value(item, "naming_sql_name", "sql_name", "name", default=""),
                        params,
                        self._value(item, "description", "desc", default=""),
                        " ".join(extra_fields),
                    ]
                ).strip()
            )
        search_text = self._join_parts(
            [
                bo_name,
                description,
                " ".join(field_ids),
                " ".join(naming_sql_ids),
                " ".join(naming_sql_summaries),
                self._value(resource, "domain", default="default"),
                " ".join(self._list_value(resource, "tags")),
            ]
        )
        return ResourceDocument(
            resource_id=self._value(resource, "resource_id", "id", default=f"bo:{bo_name}"),
            resource_type="bo",
            name=bo_name,
            description=description,
            search_text=search_text,
            domain=self._value(resource, "domain", default="default"),
            tags=self._list_value(resource, "tags"),
            raw_ref=resource,
        )

    def build_function_document(self, resource: FunctionResource) -> ResourceDocument:
        name = self._value(resource, "name", "func_name", "function_name", default="")
        full_name = self._value(resource, "full_name", "name", default=name)
        function_name = self._value(resource, "function_name", default=full_name or name)
        function_name_zh = self._value(resource, "function_name_zh", "description", "func_desc", default="")
        params = [str(item) for item in self._list_value(resource, "params")]
        param_defs = self._list_value(resource, "params_Defs", "param_defs", "param_list")
        param_names = [self._value(item, "param_name", "name", "id", default="") for item in param_defs]
        full_name_split = " ".join(
            sub
            for part in str(full_name).split(".")
            for sub in self._text_normalizer.split_identifier(part)
        )
        search_text = self._join_parts(
            [
                function_name,
                full_name,
                full_name_split,
                function_name_zh,
                self._value(resource, "function_kind", "function_type", default=""),
                " ".join(str(item) for item in [*params, *param_names] if item),
                self._value(resource, "return_type", "return_type_raw", default=""),
                " ".join(self._list_value(resource, "tags")),
            ]
        )
        return ResourceDocument(
            resource_id=self._value(resource, "resource_id", "function_id", "id", default=f"function:{full_name or name}"),
            resource_type="function",
            name=full_name or function_name,
            description=self._value(resource, "description", "func_desc", default=function_name_zh),
            search_text=search_text,
            return_type=self._value(resource, "return_type", "return_type_raw", default=""),
            tags=self._list_value(resource, "tags"),
            raw_ref=resource,
        )

    def _join_parts(self, parts: list[str]) -> str:
        return self._text_normalizer.expand_text(" ".join(part for part in parts if part).strip())

    def _value(self, resource: object, *keys: str, default: str | object = "") -> str | object:
        for key in keys:
            if isinstance(resource, dict) and key in resource and resource[key] is not None:
                return resource[key]
            if hasattr(resource, key):
                value = getattr(resource, key)
                if value is not None:
                    return value
        return default

    def _list_value(self, resource: object, *keys: str) -> list:
        value = self._value(resource, *keys, default=[])
        if isinstance(value, list):
            return value
        return []
