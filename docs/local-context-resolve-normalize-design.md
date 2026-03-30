# Local Context 路径聚合解析与 Normalize 增强设计

## 需求澄清结果
- `node_path` 采用 JSONPath（示例：`$.mapping_content.children[0].children[1]`）。
- `local_context` 来源仅限 `parent/parent_list` 节点（兼容 `parent list`）。
- `property_id` 缺失允许稳定哈希兜底。
- 同名冲突业务上不应出现，但代码保留 warning 追踪。
- `selected_local_contexts` 废弃，不再作为核心输出。
- planner/filter 仅透传必要字段。

## WHAT
1. 新增 `local_context_resolver`：按 JSONPath 逐段下钻，恢复根到目标路径链，并聚合路径上所有节点的 `local_context`。
2. 新增 `local_context_normalizer`：生成独立 local context 标准结构（`resource_id/property_id/property_name/access_path/source_trace/warnings`）。
3. 环境接入：`FilteredEnvironment` 新增 `visible_local_context`，停止将 local context 注入 global context registry。
4. 消费接入：planner、validator、ast builder 改为消费 `visible_local_context`。
5. 补充测试：覆盖路径聚合、access_path、resource_id 覆盖规则、JSONPath 解析、registry 边界。

## WHY
- local context 与 global context 来源和语义不同，必须分离建模。
- 可见性规则是“根到目标路径聚合”，不能只看父节点。
- `property_id` 用于稳定定位与覆盖；`property_name` 用于表达式 `$local$.{property_name}`。

## HOW
- JSONPath 解析步骤：`$` + `.key` + `[index]`，逐层访问并记录 traversed nodes。
- resolver 输出 `RawLocalContextWithSource(payload, source_node_path, source_node_id, depth)`。
- normalizer 输出 `VisibleLocalContextSet`，规则：
  - 同 `property_id`：近端覆盖远端并记录 trace。
  - 同 `property_name` 不同 `property_id`：记录 warning，近端优先。
- planner local 透传字段：`resource_id/property_id/property_name/access_path/annotation`。
