# 开发计划：DSL Agent Datatype 同链路生成

## Stage #1 运行时配置与模型扩展

### Task #1：RuntimeConfig 模型与加载器
- 内容：新增 runtime config/datatype defaults 强类型模型与 `RuntimeConfigLoader`，实现 site_level_config 归一化与 fail-fast 校验。
- 预期结果：`DSLAgent` 初始化可拿到可访问、可校验的 `datatype_defaults`（time/money/flow）。
- 状态：Finished

### Task #2：响应与计划模型扩展
- 内容：扩展 `GenerateDSLResponse` 与相关 debug/validation 模型，新增 datatype 输出结构。
- 预期结果：响应模型支持 `datatype`、`datatype_plan`、`datatype_validation`。
- 状态：Finished

## Stage #2 Datatype 判定、补全与统一校验

### Task #1：DatatypeClassifier + DatatypeResolver
- 内容：实现规则优先分类器与 defaults 优先补全器，支持 time/money 局部覆写逻辑。
- 预期结果：可根据 query/node 语义输出完整 datatype dict。
- 状态：Finished

### Task #2：ExpressionRefValidator + DatatypeValidator
- 内容：实现表达式统一引用校验，并在 datatype 校验中复用。
- 预期结果：datatype 所有 `*_expression` 进入统一校验路径，非法值可准确报错。
- 状态：Finished

### Task #3：DSLAgent 主链路集成
- 内容：在 `generate_dsl` 中串联 classify/resolve/validate，并统一 success 判定与 debug 输出。
- 预期结果：主表达式与 datatype 同链路生成、同链路校验、同链路输出。
- 状态：Finished

## Stage #3 测试与回归

### Task #1：datatype 主链路测试
- 内容：覆盖 simple_string/time/money 三类输出与 debug 字段。
- 预期结果：主流程测试验证 datatype 必返与核心语义。
- 状态：Finished

### Task #2：配置/表达式异常测试
- 内容：覆盖非法配置 fail-fast、fake path/null/empty/unknown/TBD 校验。
- 预期结果：错误路径稳定可复现。
- 状态：Finished

### Task #3：回归测试与文档同步
- 内容：运行现有测试回归，必要时补充说明文档与 TODO 假设点。
- 预期结果：改造不破坏既有主链路能力。
- 状态：Finished
