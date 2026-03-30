# OpenAILLMClient 单一化收敛设计

## 背景
用户要求不做兼容，仅保留一个类承载模型调用与结构化输出能力。当前实现存在 `OpenAILLMClient`、`StructuredLLMExecutor`、`PromptDrivenLLMService` 三个层次，职责重复。

## 澄清结果
- 保留：`OpenAILLMClient`
- 删除：`StructuredLLMExecutor`
- 删除：`PromptDrivenLLMService`
- 不保留兼容别名/协议分支

## WHAT
1. 将结构化执行能力内聚到 `OpenAILLMClient`。
2. 改造 `LLMPlanner` 与 `OpenAISemanticSelector` 直接调用 `OpenAILLMClient`。
3. 删除冗余类与导出。
4. 调整测试，覆盖结构化场景。

## WHY
- 降低抽象层级，减少维护面。
- 避免“请求在 client、解析在 executor”的职责分裂。
- 满足“只保留一个类”的明确要求。

## HOW
- 在 `llm_client.py` 增加结构化结果模型与 `execute_structured`。
- 迁移原 executor 的错误码、解析逻辑、attempt 记录。
- 调用方从 `executor.execute` 替换为 `client.execute_structured`。
- 删除 `services/structured_llm_executor.py` 与 `services/llm_service.py`。
