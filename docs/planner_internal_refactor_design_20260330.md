# Planner 内部重构设计（2026-03-30）

## 背景
当前 `LLMPlanner.plan` 单次调用把意图理解、模式判断、资源选择、参数规划、表达式组装全部塞进一个 prompt，造成输入过长、约束执行稳定性下降。

## 澄清结论
- 本次仅重构 planner 内部，不改 planner 对外签名和返回结构。
- 主链路 `agent -> ... -> planner -> validator -> ast builder` 保持不变。
- 保留现有 repair 入口与协议。
- 允许在 planner 内部增加阶段模型、编排器、资源裁剪与回退机制。

## WHAT（做什么）
将 planner 内部改为三段式隐式编排（对外仍是一次 `plan`）：
1. **Skeleton Planning**：产出高层规划骨架（是否需要 context/BO/function/namingSQL/binding）。
2. **Detail Planning**：在 skeleton 约束下，仅输入必要资源，生成 detail payload（可直接 ProgramPlan，或带 `plan` 字段）。
3. **Final Assembly**：内部组装并解析成最终 `ProgramPlan`。

并在阶段失败时实施局部回退：
- skeleton/detail/assembly 任一失败时，回退到 legacy 单段 plan（保障兼容和可用性）。
- repair 逻辑保持原有单入口，不影响 validator 与 ast builder。

## WHY（为什么）
- **缩短单次 prompt**：skeleton 仅用摘要，不再灌入全量资源明细。
- **按需喂数**：detail 根据 skeleton 裁剪环境，减少不相关候选干扰。
- **稳定性提升**：职责分离后，模型更易遵守阶段性约束。
- **兼容安全**：最终仍输出 `ProgramPlan`，外部调用无需改造。

## HOW（怎么做）
- 在 `billing_dsl_agent/llm_planner.py` 新增内部结构：
  - `PlannerSkeleton`
  - `PlannerDetail`
  - `PlannerWorkingContext`
  - `PlannerStageResult`
- 在 `LLMPlanner.plan` 中新增内部阶段编排：
  - `_build_working_context`
  - `_run_skeleton_stage`
  - `_run_detail_stage`
  - `_assemble_final_plan`
  - `_run_legacy_plan`（兼容兜底）
- 增加 prompt：
  - `dsl_plan_skeleton_prompt`
  - `dsl_plan_detail_prompt`
- 增加/修改 planner 内部单测，验证：
  - 外部入口和输出兼容
  - 阶段执行与资源裁剪行为正确
  - 阶段失败回退可用
  - repair 未受破坏

## 不改动范围
- agent entry
- loader/normalize（context/BO/function）
- environment/resource manager
- validator
- ast builder
- edsl renderer
- request/response 顶层数据结构
