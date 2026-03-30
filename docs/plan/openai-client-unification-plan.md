# OpenAILLMClient 单一化收敛计划

## Stage 1：能力收敛到 OpenAILLMClient
- Task 1.1 在 client 新增 `execute_structured`。
- Task 1.2 移除兼容别名 `generate/generate_raw`。
- Task 1.3 将 executor 关键测试迁移到 client 测试。

## Stage 2：调用方切换与冗余删除
- Task 2.1 `LLMPlanner` 切换为直接依赖 client。
- Task 2.2 `OpenAISemanticSelector` 切换为直接依赖 client。
- Task 2.3 删除 `StructuredLLMExecutor`、`PromptDrivenLLMService` 及导出。

## Stage 3：验证与交付
- Task 3.1 运行相关测试/检查。
- Task 3.2 追加 `progress.md` 记录。
- Task 3.3 提交并创建 PR。
