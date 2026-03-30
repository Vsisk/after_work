# OpenAI 多模型（文本 + VL）基类抽象设计

## 需求背景
当前仓库仅有单一 `OpenAILLMClient`，默认依赖一套 `OPENAI_*` 环境变量，不支持：
1. 通过 `llm_name` 切换不同模型配置；
2. 图像输入（VL）调用；
3. 文本与 VL 的统一抽象基类。

## 澄清结果
根据用户确认：
1. 抽象范围：仅 OpenAI provider 内多模型（文本 + VL）。
2. 图像输入首期支持：`image_url` + 本地文件路径（路径会转 base64 data URL）。
3. `.env` 配置命名：采用 `LLM_<NAME>_<FIELD>` 方案。
4. 路由规则：调用不传 `llm_name` 时使用 `LLM_DEFAULT_NAME`，也支持显式覆盖传参。

## WHAT
1. 抽象一个 OpenAI 场景可复用的基类（例如 `BaseOpenAILLMClient`），负责：
   - 加载与解析 `.env` 多模型配置；
   - 按 `llm_name` 解析模型参数；
   - 统一请求与错误处理。
2. 在基类上实现具体客户端（`OpenAILLMClient`），同时支持：
   - 文本输入调用；
   - VL 输入调用（image_url / 本地图片路径）。
3. 保持现有结构化执行能力（`execute_structured`）可用，并支持 `llm_name` 路由。

## WHY
1. 避免每增加一个模型都复制一套 client 配置逻辑。
2. 将“模型配置管理”从业务调用点剥离，统一由 client 内处理。
3. 支持 VL 能力，满足图像理解需求并与文本能力共享调用入口。

## HOW

### 1) `.env` 配置规范
- 默认模型名：
  - `LLM_DEFAULT_NAME=text_default`
- 命名模型配置（以 `text_default` 为例，最终 key 为大写）：
  - `LLM_TEXT_DEFAULT_MODEL=gpt-4.1-mini`
  - `LLM_TEXT_DEFAULT_API_KEY=...`
  - `LLM_TEXT_DEFAULT_BASE_URL=https://api.openai.com/v1`
  - `LLM_TEXT_DEFAULT_CHAT_COMPLETIONS_PATH=/chat/completions`
  - `LLM_TEXT_DEFAULT_TIMEOUT=60`

VL 模型可独立命名，例如 `vl_default`：
- `LLM_VL_DEFAULT_MODEL=gpt-4.1`
- `LLM_VL_DEFAULT_API_KEY=...`
- `LLM_VL_DEFAULT_BASE_URL=...`
- `LLM_VL_DEFAULT_CHAT_COMPLETIONS_PATH=...`
- `LLM_VL_DEFAULT_TIMEOUT=...`

### 2) 新增模型配置数据结构
新增 `LLMConfig`（dataclass）：
- `name`
- `model`
- `api_key`
- `base_url`
- `chat_completions_path`
- `timeout`

### 3) 基类职责（BaseOpenAILLMClient）
- 解析 env / 系统环境变量；
- 根据 `llm_name` 构建 `LLMConfig`（含 fallback：`LLM_DEFAULT_NAME`）；
- 提供统一 `transport` 请求能力。

### 4) OpenAILLMClient 扩展
- `invoke` / `invoke_raw`：新增可选参数 `llm_name`；
- `invoke_multimodal` / `invoke_multimodal_raw`：支持文本 + 图像输入；
- `execute_structured`：支持 `llm_name`，行为与现有一致。

### 5) VL 请求体约定
对 OpenAI chat-completions `messages[0].content` 使用数组：
- 文本块：`{"type":"text","text":"..."}`
- 图像块：
  - URL：`{"type":"image_url","image_url":{"url":"https://..."}}`
  - 本地路径：读取文件后转 `data:image/<ext>;base64,<...>` 填入同一字段。

### 6) 错误处理
新增错误码建议：
- `llm_config_not_found`
- `invalid_image_input`
- `image_read_error`

### 7) 兼容策略
- 现有调用若不传 `llm_name`，继续可用（使用 `LLM_DEFAULT_NAME`）。
- 原 `OPENAI_*` 作为兜底保留一版（迁移期），优先读取 `LLM_<NAME>_*`。

## 非目标
- 本次不引入多 provider（如 Anthropic、Gemini）。
- 本次不实现视频/音频多模态输入。
