# 开发计划：查询表达式与 NamingSQL 强校验

## Phase #1 方案与模型重构

### Task #1：查询 AST 结构设计与落地
- 内容：扩展 ProgramPlan/ExprPlanNode，支持 where 布尔 AST 与 fetch pair 参数结构。
- 预期结果：模型层可表达 select/fetch 两类查询语义差异。
- 状态：Finished

### Task #2：Prompt 协议更新
- 内容：更新 plan_prompt/repair_prompt，要求 LLM 产出新结构并理解错误码。
- 预期结果：LLM 输出计划可被新 validator 正确解析与修复。
- 状态：Finished

## Phase #2 校验与渲染增强

### Task #1：PlanValidator 强校验实现
- 内容：新增 query shape 校验、where AST 校验、naming-sql 参数一致性校验。
- 预期结果：不符合语义的计划在校验阶段被识别并输出可修复 issue。
- 状态：Finished

### Task #2：ASTBuilder 与 DSLRenderer 改造
- 内容：支持新 AST 到 ExprNode 转换；fetch/fetch_one 渲染 naming-sql 名称与 pair。
- 预期结果：生成 DSL 文本符合目标语法。
- 状态：Finished

## Phase #3 测试与回归

### Task #1：单元测试
- 内容：新增 where AST、naming-sql 参数一致性、错误码覆盖测试。
- 预期结果：核心规则有可复查测试保护。
- 状态：Finished

### Task #2：主流程集成测试
- 内容：新增 generate -> validate -> repair -> render 闭环测试。
- 预期结果：失败可修复路径稳定。
- 状态：Finished

### Task #3：回归与文档更新
- 内容：校验现有测试兼容性，补充 README/架构文档差异说明。
- 预期结果：改造后行为可追溯、可维护。
- 状态：Finished
