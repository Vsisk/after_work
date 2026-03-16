"""Default environment resolver service."""

from __future__ import annotations

from typing import Iterable, List, Sequence

from billing_dsl_agent.types.bo import BODef, BOFieldDef, BOQueryCapability, NamingSQLDef, RwRuleTerm
from billing_dsl_agent.types.common import ContextScope
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef, FunctionParamDef, FunctionTypeRef
from billing_dsl_agent.types.plan import ResolvedEnvironment


def flatten_context_fields(context_var: ContextVarDef | None) -> list[str]:
    """Return stable flattened field paths for one context variable."""

    if context_var is None:
        return []

    names: list[str] = []
    seen: set[str] = set()
    for field in context_var.fields or []:
        field_name = (field.name or "").strip()
        if not field_name or field_name in seen:
            continue
        seen.add(field_name)
        names.append(field_name)
    return names


def detect_context_name_conflicts(
    global_context_vars: Sequence[ContextVarDef] | None,
    local_context_vars: Sequence[ContextVarDef] | None,
) -> list[str]:
    """Detect same-name context variables across global and local scopes."""

    global_names = {
        _normalize_name(var.name)
        for var in (global_context_vars or [])
        if isinstance(var, ContextVarDef) and _normalize_name(var.name)
    }
    local_names = {
        _normalize_name(var.name)
        for var in (local_context_vars or [])
        if isinstance(var, ContextVarDef) and _normalize_name(var.name)
    }
    return sorted(global_names & local_names)


def merge_visible_context_vars(
    global_context_vars: Sequence[ContextVarDef] | None,
    local_context_vars: Sequence[ContextVarDef] | None,
) -> list[ContextVarDef]:
    """Merge visible context vars for consumers that need node-level visibility."""

    visible: list[ContextVarDef] = []
    local_by_name = {
        _normalize_name(var.name): clone_context_var(var, ContextScope.LOCAL)
        for var in (local_context_vars or [])
        if isinstance(var, ContextVarDef) and _normalize_name(var.name)
    }

    for var in local_by_name.values():
        visible.append(var)

    for global_var in global_context_vars or []:
        if not isinstance(global_var, ContextVarDef):
            continue
        key = _normalize_name(global_var.name)
        if not key or key in local_by_name:
            continue
        visible.append(clone_context_var(global_var, ContextScope.GLOBAL))

    return visible


def clone_context_var(context_var: ContextVarDef, scope: ContextScope | None = None) -> ContextVarDef:
    """Clone one context variable and normalize its fields."""

    normalized_scope = scope or context_var.scope
    fields = _normalize_context_fields(context_var.fields)
    return ContextVarDef(
        name=(context_var.name or "").strip(),
        scope=normalized_scope,
        data_type=context_var.data_type,
        description=context_var.description,
        nullable=context_var.nullable,
        fields=fields,
        inherited_from=context_var.inherited_from,
    )


class DefaultEnvironmentResolver:
    """Resolve request resources into a stable environment."""

    def resolve(
        self,
        global_context_vars: List[ContextVarDef] | None,
        local_context_vars: List[ContextVarDef] | None,
        available_bos: List[BODef] | None,
        available_functions: List[FunctionDef] | None,
    ) -> ResolvedEnvironment:
        normalized_global = self._normalize_context_vars(global_context_vars, ContextScope.GLOBAL)
        normalized_local = self._normalize_context_vars(local_context_vars, ContextScope.LOCAL)

        # TODO: expose conflicts through a dedicated issues model once ResolvedEnvironment supports it.
        _ = detect_context_name_conflicts(normalized_global, normalized_local)

        return ResolvedEnvironment(
            global_context_vars=normalized_global,
            local_context_vars=normalized_local,
            available_bos=self._normalize_bos(available_bos),
            available_functions=self._normalize_functions(available_functions),
        )

    def _normalize_context_vars(
        self,
        context_vars: Sequence[ContextVarDef] | None,
        scope: ContextScope,
    ) -> list[ContextVarDef]:
        deduped: list[ContextVarDef] = []
        by_name: dict[str, ContextVarDef] = {}

        for raw_var in context_vars or []:
            if not isinstance(raw_var, ContextVarDef):
                continue

            name = (raw_var.name or "").strip()
            key = _normalize_name(name)
            if not key:
                continue

            normalized = clone_context_var(raw_var, scope)
            if key in by_name:
                by_name[key] = self._merge_context_var(by_name[key], normalized, scope)
            else:
                by_name[key] = normalized

        for raw_var in context_vars or []:
            if not isinstance(raw_var, ContextVarDef):
                continue
            key = _normalize_name(raw_var.name)
            if not key or key not in by_name:
                continue
            current = by_name.pop(key)
            deduped.append(current)

        return deduped

    def _merge_context_var(
        self,
        base: ContextVarDef,
        incoming: ContextVarDef,
        scope: ContextScope,
    ) -> ContextVarDef:
        merged_fields = _merge_context_fields(base.fields, incoming.fields)
        description = base.description or incoming.description
        inherited_from = base.inherited_from or incoming.inherited_from
        nullable = base.nullable and incoming.nullable
        data_type = base.data_type if str(base.data_type) != "DSLDataType.UNKNOWN" else incoming.data_type
        return ContextVarDef(
            name=base.name,
            scope=scope,
            data_type=data_type,
            description=description,
            nullable=nullable,
            fields=merged_fields,
            inherited_from=inherited_from,
        )

    def _normalize_bos(self, available_bos: Sequence[BODef] | None) -> list[BODef]:
        deduped: list[BODef] = []
        seen: set[str] = set()

        for bo in available_bos or []:
            if not isinstance(bo, BODef):
                continue
            key = _normalize_name(bo.name) or _normalize_name(bo.id)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(_clone_bo(bo))

        return deduped

    def _normalize_functions(self, available_functions: Sequence[FunctionDef] | None) -> list[FunctionDef]:
        deduped: list[FunctionDef] = []
        seen: set[str] = set()

        for fn in available_functions or []:
            if not isinstance(fn, FunctionDef):
                continue
            key = _normalize_name(fn.full_name) or _normalize_name(fn.method_name)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(_clone_function(fn))

        return deduped


def _normalize_context_fields(fields: Iterable[ContextFieldDef] | None) -> list[ContextFieldDef]:
    deduped: list[ContextFieldDef] = []
    seen: set[str] = set()

    for field in fields or []:
        if not isinstance(field, ContextFieldDef):
            continue
        name = (field.name or "").strip()
        key = _normalize_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(
            ContextFieldDef(
                name=name,
                data_type=field.data_type,
                description=field.description,
                nullable=field.nullable,
            )
        )

    return deduped


def _merge_context_fields(
    base_fields: Sequence[ContextFieldDef] | None,
    incoming_fields: Sequence[ContextFieldDef] | None,
) -> list[ContextFieldDef]:
    merged: dict[str, ContextFieldDef] = {}

    for field in list(base_fields or []) + list(incoming_fields or []):
        if not isinstance(field, ContextFieldDef):
            continue
        key = _normalize_name(field.name)
        if not key:
            continue
        normalized = ContextFieldDef(
            name=(field.name or "").strip(),
            data_type=field.data_type,
            description=field.description,
            nullable=field.nullable,
        )
        if key in merged:
            existing = merged[key]
            data_type = existing.data_type if str(existing.data_type) != "DSLDataType.UNKNOWN" else normalized.data_type
            merged[key] = ContextFieldDef(
                name=existing.name,
                data_type=data_type,
                description=existing.description or normalized.description,
                nullable=existing.nullable and normalized.nullable,
            )
        else:
            merged[key] = normalized

    return list(merged.values())


def _clone_bo(bo: BODef) -> BODef:
    return BODef(
        id=bo.id,
        name=bo.name,
        description=bo.description,
        source=bo.source,
        is_virtual=bo.is_virtual,
        fields=[
            BOFieldDef(
                name=field.name,
                type=field.type,
                description=field.description,
                nullable=field.nullable,
                metadata=dict(field.metadata),
            )
            for field in bo.fields
        ],
        rw_rule_list=[
            RwRuleTerm(
                rw_rule_id=rule.rw_rule_id,
                app_scene=rule.app_scene,
                read_or_mapping_id=rule.read_or_mapping_id,
                insert_or_mapping_id=rule.insert_or_mapping_id,
                update_or_mapping_id=rule.update_or_mapping_id,
                delete_or_mapping_id=rule.delete_or_mapping_id,
            )
            for rule in bo.rw_rule_list
        ],
        query_capability=BOQueryCapability(
            supports_select=bo.query_capability.supports_select,
            supports_select_one=bo.query_capability.supports_select_one,
            naming_sqls=[
                NamingSQLDef(
                    id=item.id,
                    name=item.name,
                    label=item.label,
                    description=item.description,
                    sql=item.sql,
                    params=list(item.params),
                    returns_list=item.returns_list,
                    is_customized=item.is_customized,
                    is_sync=item.is_sync,
                    metadata=dict(item.metadata),
                )
                for item in bo.query_capability.naming_sqls
            ],
        ),
        metadata=dict(bo.metadata),
    )


def _clone_function(fn: FunctionDef) -> FunctionDef:
    return FunctionDef(
        id=fn.id,
        class_name=fn.class_name,
        method_name=fn.method_name,
        description=fn.description,
        scope=fn.scope,
        params=[
            FunctionParamDef(
                name=param.name,
                type=FunctionTypeRef(
                    kind=param.type.kind,
                    name=param.type.name,
                    is_list=param.type.is_list,
                    metadata=dict(param.type.metadata),
                ),
                description=param.description,
                required=param.required,
                metadata=dict(param.metadata),
            )
            for param in fn.params
        ],
        return_type=(
            FunctionTypeRef(
                kind=fn.return_type.kind,
                name=fn.return_type.name,
                is_list=fn.return_type.is_list,
                metadata=dict(fn.return_type.metadata),
            )
            if fn.return_type is not None
            else None
        ),
        is_native=fn.is_native,
        need_import=fn.need_import,
        import_path=fn.import_path,
        func_so=fn.func_so,
        metadata=dict(fn.metadata),
    )


def _normalize_name(value: str | None) -> str:
    return (value or "").strip().lower()
