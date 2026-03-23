from billing_dsl_agent.models import NodeDef
from billing_dsl_agent.resource_manager import ResourceManager


def _sample_contexts() -> list[dict]:
    return [
        {"path": "$ctx$.customer.gender", "name": "gender", "description": "客户性别"},
        {"path": "$ctx$.customer.title", "name": "title", "description": "客户称谓"},
        {"path": "$ctx$.customer.salutation", "name": "salutation", "description": "称谓别名"},
        {"path": "$ctx$.prepareId", "name": "prepareId", "description": "预处理主键"},
        {"path": "$ctx$.billCycleId", "name": "billCycleId", "description": "账期标识"},
    ]


def _sample_bos() -> list[dict]:
    return [
        {
            "bo_name": "BB_PREP_SUB",
            "description": "预处理子表",
            "fields": ["prepareId", "billCycleId", "regionId"],
            "naming_sqls": ["QUERY_BY_PREPARE_AND_CYCLE"],
        }
    ]


def _sample_functions() -> list[dict]:
    return [
        {
            "full_name": "Common.Double2Str",
            "description": "数值转两位小数字符串",
            "params": ["number", "precision"],
        },
        {
            "full_name": "Customer.GetSalutation",
            "description": "根据性别返回称谓",
            "params": ["gender"],
        },
    ]


def test_build_indexes_basic() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())

    assert "$ctx$.customer.gender" in indexes.context_by_path
    assert "gender" in indexes.context_by_name
    assert "bbprepsub" in indexes.bo_by_name
    assert "regionid" in indexes.bo_field_index
    assert "querybyprepareandcycle" in indexes.naming_sql_by_name
    assert "commondouble2str" in indexes.function_by_full_name
    assert "getsalutation" in indexes.function_by_name


def test_select_candidates_by_node_semantics() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())
    node = NodeDef(
        node_id="n1",
        node_path="invoice.customerTitle",
        node_name="customerTitle",
        description="根据客户性别生成称谓",
    )

    candidates = manager.select_candidates(user_query="", node_def=node, indexes=indexes)
    context_names = {item.name for item in candidates.context_candidates}
    function_names = {item.full_name for item in candidates.function_candidates}

    assert "gender" in context_names
    assert "title" in context_names or "salutation" in context_names
    assert "Customer.GetSalutation" in function_names


def test_select_candidates_by_query_keywords() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())
    node = NodeDef(node_id="n2", node_path="invoice.region", node_name="region")

    candidates = manager.select_candidates(
        user_query="根据 prepareId 和 billCycleId 查询 BB_PREP_SUB，取 regionId",
        node_def=node,
        indexes=indexes,
    )

    context_paths = {item.path for item in candidates.context_candidates}
    bo_names = {item.bo_name for item in candidates.bo_candidates}

    assert "$ctx$.prepareId" in context_paths
    assert "$ctx$.billCycleId" in context_paths
    assert "BB_PREP_SUB" in bo_names

    matched_bo = next(item for item in candidates.bo_candidates if item.bo_name == "BB_PREP_SUB")
    assert "regionId" in matched_bo.fields
    assert "QUERY_BY_PREPARE_AND_CYCLE" in matched_bo.naming_sqls


def test_select_candidates_apply_budget() -> None:
    manager = ResourceManager()
    contexts = _sample_contexts() + [
        {"path": f"$ctx$.ext.field{i}", "name": f"field{i}", "description": "扩展字段"}
        for i in range(20)
    ]
    indexes = manager.build_indexes(contexts, _sample_bos(), _sample_functions())
    node = NodeDef(node_id="n3", node_path="invoice.amount", node_name="amount", description="金额字段")

    candidates = manager.select_candidates(
        user_query="金额和称谓都需要",
        node_def=node,
        indexes=indexes,
        budget={"context_candidates": 3, "bo_candidates": 1, "function_candidates": 1},
    )

    assert len(candidates.context_candidates) <= 3
    assert len(candidates.bo_candidates) <= 1
    assert len(candidates.function_candidates) <= 1


def test_format_for_prompt() -> None:
    manager = ResourceManager()
    indexes = manager.build_indexes(_sample_contexts(), _sample_bos(), _sample_functions())
    node = NodeDef(node_id="n4", node_path="invoice.customer", node_name="customer")
    candidates = manager.select_candidates(
        user_query="根据 prepareId 和 billCycleId 查询 BB_PREP_SUB",
        node_def=node,
        indexes=indexes,
    )

    payload = manager.format_for_prompt(candidates)

    assert set(payload.keys()) == {"context_candidates", "bo_candidates", "function_candidates"}
    assert payload["context_candidates"]
    assert payload["bo_candidates"]
    assert payload["function_candidates"]
    assert {"path", "name", "description"}.issubset(payload["context_candidates"][0].keys())
    assert {"bo_name", "description", "fields", "naming_sqls"}.issubset(payload["bo_candidates"][0].keys())
    assert {"name", "description", "params"}.issubset(payload["function_candidates"][0].keys())
