# Phase & Task Plan

## Phase #1 结构梳理与方案固化
- Task #1: 阅读入口、loader、environment、planner、validator、ast 代码并完成设计文档（Status: Finished）

## Phase #2 资源加载与筛选主链路实现
- Task #1: 新增 loader/provider 并接入 site/project 加载（Status: Finished）
- Task #2: 新增 normalization 与 resource_id registry（Status: Finished）
- Task #3: 增强 environment 三类独立筛选与 AB 分支（Status: Finished）
- Task #4: 增加 semantic selector 抽象与 mock 实现（Status: Finished）

## Phase #3 planner/validator/ast 适配
- Task #1: planner 输入改为 filtered environment（Status: Finished）
- Task #2: validator 增加 filtered env 约束校验（Status: Finished）
- Task #3: ast builder 通过 resource_id 回查 registry（Status: Finished）

## Phase #4 测试与验证
- Task #1: 新增/改造主链路集成测试（Status: Finished）
- Task #2: 执行 pytest 并修复回归（Status: Finished）
