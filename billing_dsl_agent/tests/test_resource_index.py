from billing_dsl_agent.services.resource_index import (
    DefaultResourceIndexService,
    build_bo_field_index,
    build_bo_index,
    build_context_name_index,
    build_context_path_index,
    build_function_full_name_index,
    build_function_method_name_index,
    build_naming_sql_index,
)
from billing_dsl_agent.types.bo import BODef, BOFieldDef, BOQueryCapability, BORegistry, NamingSQLDef
from billing_dsl_agent.types.common import TypeRef
from billing_dsl_agent.types.context import ContextPropertyDef, ContextRegistry
from billing_dsl_agent.types.function import FunctionClassDef, FunctionDef, FunctionRegistry


def test_context_index_build_and_lookup() -> None:
    registry = ContextRegistry(
        global_root=ContextPropertyDef(
            id="g-root",
            name="",
            children=[
                ContextPropertyDef(
                    id="bill",
                    name="billStatement",
                    children=[ContextPropertyDef(id="prepare-id", name="prepareId")],
                )
            ],
        ),
        local_roots=[
            ContextPropertyDef(
                id="l-root",
                name="input",
                children=[ContextPropertyDef(id="prepare-id-2", name="prepareId")],
            )
        ],
    )

    path_index = build_context_path_index(registry)
    name_index = build_context_name_index(registry)

    assert path_index["$ctx$.billStatement"].id == "bill"
    assert path_index["$ctx$.billStatement.prepareId"].id == "prepare-id"
    assert path_index["$local$.input.prepareId"].id == "prepare-id-2"
    assert len(name_index["prepareId"]) == 2


def test_bo_index_build_and_lookup() -> None:
    bo_registry = BORegistry(
        system_bos=[
            BODef(
                id="bo-1",
                name="SYS_BE",
                fields=[
                    BOFieldDef(name="id", type=TypeRef(kind="basic", name="STRING")),
                    BOFieldDef(name="amount", type=TypeRef(kind="basic", name="NUMBER")),
                ],
                query_capability=BOQueryCapability(
                    naming_sqls=[
                        NamingSQLDef(id="sql-1", name="queryById"),
                        NamingSQLDef(id="sql-2", name="queryById"),
                    ]
                ),
            )
        ]
    )

    bo_index = build_bo_index(bo_registry)
    bo_field_index = build_bo_field_index(bo_registry)
    naming_sql_index = build_naming_sql_index(bo_registry)

    assert bo_index["SYS_BE"].id == "bo-1"
    assert bo_field_index["SYS_BE"]["amount"].name == "amount"
    assert naming_sql_index["queryById"].id == "sql-1"


def test_function_index_build_and_lookup() -> None:
    function_registry = FunctionRegistry(
        native_classes=[
            FunctionClassDef(
                name="Common",
                functions=[FunctionDef(id="f1", class_name="Common", method_name="Double2Str")],
            )
        ],
        predefined_classes=[
            FunctionClassDef(
                name="Text",
                functions=[FunctionDef(id="f2", class_name="Text", method_name="Double2Str")],
            )
        ],
    )

    full_name_index = build_function_full_name_index(function_registry)
    method_name_index = build_function_method_name_index(function_registry)

    assert full_name_index["Common.Double2Str"].id == "f1"
    assert full_name_index["Text.Double2Str"].id == "f2"
    assert len(method_name_index["Double2Str"]) == 2


def test_resource_index_service_build_from_registries() -> None:
    context_registry = ContextRegistry(
        global_root=ContextPropertyDef(
            id="g-root",
            name="",
            children=[ContextPropertyDef(id="bill", name="billStatement")],
        )
    )
    bo_registry = BORegistry(system_bos=[BODef(id="bo-1", name="SYS_BE")])
    function_registry = FunctionRegistry(
        native_classes=[
            FunctionClassDef(
                name="Common",
                functions=[FunctionDef(id="f1", class_name="Common", method_name="Double2Str")],
            )
        ]
    )

    service = DefaultResourceIndexService()
    indexes = service.build_from_registries(
        context_registry=context_registry,
        bo_registry=bo_registry,
        function_registry=function_registry,
    )

    assert "$ctx$.billStatement" in indexes.context_path_index
    assert "billStatement" in indexes.context_name_index
    assert "SYS_BE" in indexes.bo_index
    assert "Common.Double2Str" in indexes.function_full_name_index
    assert len(indexes.function_method_name_index["Double2Str"]) == 1
