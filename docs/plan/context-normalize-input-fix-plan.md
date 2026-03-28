# Context Normalize 输入结构修正开发计划

## Stage 1：入口与数据模型对齐
- Task 1.1：扩展 `ContextRegistry`，增加 normalized 节点与索引结构。
- Task 1.2：新增 `normalize_contexts` 入口，按 `global_context` / `sub_gobal_context` 双 root 解析。
- Task 1.3：移除 `global_context.custom_context/system_context` 合并分支，按 `global_context -> sub_properties` 直接展开。

## Stage 2：递归展开与路径规则修正
- Task 2.1：新增 `normalize_context_root` / `normalize_context_property`，从 `sub_properties` 起步递归 `children`。
- Task 2.2：新增 `is_expandable_context_type`，仅 `bo|logic|extattr` 可展开。
- Task 2.3：统一 `$ctx$...` 路径生成仅使用 `property_name`。

## Stage 3：测试与回归
- Task 3.1：改造 `test_context_loader.py` 覆盖容器输入、双 root、`context_kind`、递归与叶子判定。
- Task 3.2：覆盖 `sub_gobal_context` 兼容性与 registry 双索引检索。

## Stage 4：消费链路去重
- Task 4.1：`ResourceNormalizer` 优先使用 `ContextRegistry.nodes_by_id` 生成 `ContextResource`，避免重复结构 normalize。
