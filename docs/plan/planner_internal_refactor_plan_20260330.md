# 开发计划：planner 内部分阶段重构（2026-03-30）

## Stage 1：现状梳理与边界确认
- Task 1.1 阅读 `llm_planner.py`、`ProgramPlan` 解析与现有 planner 测试。
- Task 1.2 确认外部兼容边界（入口、返回、主链路、repair）。

## Stage 2：内部阶段拆分实现
- Task 2.1 增加内部数据结构（Skeleton/Detail/WorkingContext/StageResult）。
- Task 2.2 在 `plan()` 内部引入 skeleton -> detail -> assembly 编排。
- Task 2.3 保留 legacy 单段 planner 兜底，避免外部行为变化。

## Stage 3：Prompt 体积收敛
- Task 3.1 skeleton 阶段仅使用 query/node/resource summary。
- Task 3.2 detail 阶段基于 skeleton 按需裁剪环境资源。
- Task 3.3 assembly 阶段不再重复注入业务全量信息。

## Stage 4：测试与回归
- Task 4.1 更新 planner 测试覆盖阶段执行、资源裁剪、兼容输出。
- Task 4.2 验证 repair 流程仍可运行。
- Task 4.3 执行测试并修复回归。

## Stage 5：收尾与记录
- Task 5.1 更新 `progress.md` 追加执行记录。
- Task 5.2 git commit。
- Task 5.3 生成 PR 标题和描述。
