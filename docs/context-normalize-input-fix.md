# Context Normalize 输入结构修正设计

## 背景
当前 `context normalize` 将输入当作多个离散对象处理，且仅显式处理 `global_context` + `sub_global_context`，与线上真实容器结构不一致（真实为 `global_context` + `sub_gobal_context`）。

## 需求澄清结果
- normalize 入口固定接收容器对象：
  - `context_payload["global_context"]`
  - `context_payload["sub_gobal_context"]`
- `global_context` 当前真实结构为直接挂载 `sub_properties`，不再包含 `custom_context/system_context` 包装层
- 输入解析必须兼容真实字段 `sub_gobal_context`（保留向后兼容 `sub_global_context`）
- 两类 root context 需要分别 normalize 并打上 `context_kind`
- root 第一层字段来自 `sub_properties`；可展开类型继续递归 `children`
- `access_path` 仅用 `property_name` 拼接，格式为 `$ctx$....`

## WHAT
1. 新增 normalize 总入口 `normalize_contexts(context_payload)`。
2. 引入 `normalize_context_root` / `normalize_context_property` 递归展开。
3. 新增 `is_expandable_context_type`，统一判定可展开类型：`bo|logic|extattr`。
4. 增强 `ContextRegistry`，新增节点索引与 root/descendant 结构化索引。
5. `ResourceNormalizer` 直接消费 `ContextRegistry.nodes_by_id` 构建 `ContextResource`，避免对 context 树做二次结构归一化。

## WHY
- 与真实输入协议对齐，避免 `sub_gobal_context` 丢失。
- 为 selector/planner/ast builder 提供稳定、可检索的标准化上下文索引。
- 避免将基础标量错误递归，减少噪音节点。

## HOW
- 根节点路径：`$ctx$.{root.property_name}`。
- 子节点路径：`{parent_path}.{property_name}`。
- 每个节点生成标准信息：`resource_id`、`context_kind`、`access_path`、`parent_resource_id`、`depth`、`return_type` 等。
- registry 提供：`nodes_by_id`、`nodes_by_access_path`、`descendants_by_root_context`、`roots_by_context_kind`。
