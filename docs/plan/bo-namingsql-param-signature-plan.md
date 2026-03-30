# BO namingSQL 参数类型签名增强开发计划

关联设计文档：`docs/bo-namingsql-param-signature-design.md`

## Phase #1 模型与 BO 资源规范化（Status: Finished）
- Task #1（Finished）：新增 namingSQL 标准化模型与 `BOResource` 扩展字段。
- Task #2（Finished）：ResourceNormalizer 构建 namingSQL 参数签名与回查索引。

## Phase #2 ResourceManager 与 Validator 接入（Status: Finished）
- Task #1（Finished）：BO candidate `naming_sqls` 升级为结构化签名输出。
- Task #2（Finished）：接入 `compare_namingsql_param_type` 与 namingSQL 参数签名校验链路。

## Phase #3 测试与收尾（Status: Finished）
- Task #1（Finished）：补充 loader/resource_manager/validator 测试。
- Task #2（Finished）：更新进度记录并完成分阶段提交。
