# DSL Agent Datatype 同链路生成设计

## 背景与目标

当前系统外层默认将节点 datatype 固定为 `simple_string`，导致时间/金额场景语义缺失。此次改造要求在 DSL Agent 内部与主表达式生成同链路地产生 datatype，并完成补全与校验。

## 需求澄清结论

1. 保持现有 `generate_dsl` 与 `GenerateDSLResponse`，通过字段扩展实现能力升级。
2. `datatype` 字段在成功响应中强制返回（含 `simple_string`）。
3. runtime config 非法时在 `DSLAgent` 初始化阶段 fail-fast 报错。
4. datatype 覆写策略采用“默认优先 + 规则覆写”。
5. 新增统一 `ExpressionRefValidator`，主链路与 datatype expression 复用。
6. debug 输出字段使用：`plan` / `datatype_plan` / `validation` / `datatype_validation`。
7. `flow_type_config` 本期仅接入归一化与扩展预留，不作为正式输出 datatype。

## WHAT

- 新增 runtime config 归一化与 fail-fast 校验能力。
- 新增 datatype 模型、分类器、补全器、校验器。
- 将 datatype 判定/补全/校验嵌入 `DSLAgent.generate_dsl` 主链路。
- 扩展 `GenerateDSLResponse`，统一输出 datatype 和 debug 结果。
- 补充覆盖 simple_string/time/money 与异常路径测试。

## WHY

- 避免外层硬编码 datatype，减少语义漂移。
- 优先使用稳定配置，避免 LLM 自由生成全部字段。
- 复用统一表达式校验，防止 datatype “伪成功不可执行”。

## HOW

- 新增模块：
  - `runtime_config_loader.py`
  - `datatype_models.py`
  - `datatype_classifier.py`
  - `datatype_resolver.py`
  - `expression_ref_validator.py`
  - `datatype_validator.py`
- 修改模块：
  - `agent_entry.py`
  - `models.py`
  - `tests/test_agent_main_flow.py`
  - 新增 `tests/test_datatype_pipeline.py`
- 主流程：plan -> render -> classify datatype -> resolve datatype -> validate datatype -> unified response。

## 测试与验收

1. simple_string 默认输出。
2. time 默认补全与格式覆写。
3. money 默认补全与币种表达式覆写。
4. 非法 config 初始化失败。
5. datatype expression 非法值识别。
6. debug 输出包含 datatype_plan/datatype_validation。
