# Local Context 路径聚合解析与 Normalize 开发计划

## Stage 1：模型与解析（Status: Finished）
- Task 1.1（Finished）：新增 local context 专属模型（raw/normalized/visible set）。
- Task 1.2（Finished）：实现 JSONPath 解析与路径链恢复。
- Task 1.3（Finished）：实现 resolver，收集路径链上的 local_context。

## Stage 2：Normalize 与冲突规则（Status: Finished）
- Task 2.1（Finished）：实现 `$local$.{property_name}` access_path 生成。
- Task 2.2（Finished）：实现 property_id 稳定 resource_id + 缺失兜底。
- Task 2.3（Finished）：实现覆盖/冲突规则与 warning/source_trace。

## Stage 3：环境与消费接入（Status: Finished）
- Task 3.1（Finished）：EnvironmentBuilder 注入 `visible_local_context`，不再混入 `registry.contexts`。
- Task 3.2（Finished）：LLM planner local payload 改为精简结构。
- Task 3.3（Finished）：validator / ast builder 本地引用解析接入。

## Stage 4：测试与回归（Status: Finished）
- Task 4.1（Finished）：新增 local context 路径聚合与冲突规则测试。
- Task 4.2（Finished）：更新主流程测试以匹配新链路。
