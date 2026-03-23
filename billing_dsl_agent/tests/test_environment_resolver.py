from billing_dsl_agent.services.environment_resolver import (
    DefaultEnvironmentResolver,
    detect_context_name_conflicts,
    flatten_context_fields,
    merge_visible_context_vars,
)
from billing_dsl_agent.types.bo import BODef
from billing_dsl_agent.types.common import ContextScope, DSLDataType
from billing_dsl_agent.types.context import ContextFieldDef, ContextVarDef
from billing_dsl_agent.types.function import FunctionDef


def test_environment_resolver_basic() -> None:
    resolver = DefaultEnvironmentResolver()

    resolved = resolver.resolve(
        global_context_vars=[
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                data_type=DSLDataType.OBJECT,
                fields=[
                    ContextFieldDef(name="gender", data_type=DSLDataType.STRING),
                    ContextFieldDef(name="gender", data_type=DSLDataType.STRING),
                    ContextFieldDef(name="name", data_type=DSLDataType.STRING),
                ],
            ),
            ContextVarDef(
                name="customer",
                scope=ContextScope.GLOBAL,
                data_type=DSLDataType.OBJECT,
                fields=[ContextFieldDef(name="level", data_type=DSLDataType.STRING)],
            ),
        ],
        local_context_vars=[
            ContextVarDef(
                name="item",
                scope=ContextScope.LOCAL,
                data_type=DSLDataType.OBJECT,
                fields=[ContextFieldDef(name="amount", data_type=DSLDataType.NUMBER)],
            )
        ],
        available_bos=[BODef(id="bo_customer", name="CustomerBO"), BODef(id="bo_customer", name="CustomerBO")],
        available_functions=[
            FunctionDef(id="fn_1", class_name="Common", method_name="Double2Str"),
            FunctionDef(id="fn_1", class_name="Common", method_name="Double2Str"),
        ],
    )

    assert len(resolved.global_context_vars) == 1
    assert resolved.global_context_vars[0].name == "customer"
    assert flatten_context_fields(resolved.global_context_vars[0]) == ["gender", "name", "level"]
    assert len(resolved.local_context_vars) == 1
    assert resolved.local_context_vars[0].name == "item"
    assert len(resolved.available_bos) == 1
    assert resolved.available_bos[0].name == "CustomerBO"
    assert len(resolved.available_functions) == 1
    assert resolved.available_functions[0].full_name == "Common.Double2Str"


def test_environment_resolver_handles_empty_inputs() -> None:
    resolver = DefaultEnvironmentResolver()

    resolved = resolver.resolve(
        global_context_vars=None,
        local_context_vars=None,
        available_bos=None,
        available_functions=None,
    )

    assert resolved.global_context_vars == []
    assert resolved.local_context_vars == []
    assert resolved.available_bos == []
    assert resolved.available_functions == []
    assert merge_visible_context_vars(resolved.global_context_vars, resolved.local_context_vars) == []
    assert detect_context_name_conflicts(resolved.global_context_vars, resolved.local_context_vars) == []


def test_environment_resolver_context_name_conflict() -> None:
    resolver = DefaultEnvironmentResolver()
    global_customer = ContextVarDef(
        name="customer",
        scope=ContextScope.GLOBAL,
        data_type=DSLDataType.OBJECT,
        fields=[ContextFieldDef(name="gender", data_type=DSLDataType.STRING)],
    )
    local_customer = ContextVarDef(
        name="customer",
        scope=ContextScope.LOCAL,
        data_type=DSLDataType.OBJECT,
        fields=[ContextFieldDef(name="nickname", data_type=DSLDataType.STRING)],
    )

    resolved = resolver.resolve(
        global_context_vars=[global_customer],
        local_context_vars=[local_customer],
        available_bos=[],
        available_functions=[],
    )

    conflicts = detect_context_name_conflicts(resolved.global_context_vars, resolved.local_context_vars)
    visible = merge_visible_context_vars(resolved.global_context_vars, resolved.local_context_vars)

    assert conflicts == ["customer"]
    assert len(resolved.global_context_vars) == 1
    assert len(resolved.local_context_vars) == 1
    assert resolved.global_context_vars[0].scope == ContextScope.GLOBAL
    assert resolved.local_context_vars[0].scope == ContextScope.LOCAL
    assert len(visible) == 1
    assert visible[0].name == "customer"
    assert visible[0].scope == ContextScope.LOCAL
    assert flatten_context_fields(visible[0]) == ["nickname"]
