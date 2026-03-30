# OpenAI 多模型（文本 + VL）开发计划

关联设计文档：`docs/openai-multi-model-vl-design.md`

## Stage 1：配置抽象与基类落地

### Task 1.1 新增配置模型
- 增加 `LLMConfig` 数据结构。

### Task 1.2 新增基类
- 新建 `BaseOpenAILLMClient`（或等价命名），实现：
  - env 解析；
  - `llm_name -> config` 路由；
  - 默认模型名兜底。

### Task 1.3 回归文本调用
- `OpenAILLMClient.invoke/invoke_raw/execute_structured` 接入 `llm_name`。

## Stage 2：VL 能力接入

### Task 2.1 定义多模态输入协议
- 设计 `image_url` + `image_path` 输入参数。

### Task 2.2 实现多模态调用
- 新增 `invoke_multimodal` / `invoke_multimodal_raw`。
- 本地路径读取并转换 data URL。

### Task 2.3 错误处理
- 增加配置缺失、图片读取失败、非法输入错误码与异常信息。

## Stage 3：测试与交付

### Task 3.1 单测
- 多 `llm_name` 配置解析与路由。
- 默认 `LLM_DEFAULT_NAME` 生效。
- VL URL / 本地路径调用请求体验证。
- 错误分支覆盖。

### Task 3.2 进度记录
- 在 `progress.md` 追加本次执行记录。

### Task 3.3 提交与 PR
- 每个 stage 完成后提交。
- 最终整理 PR 说明。
