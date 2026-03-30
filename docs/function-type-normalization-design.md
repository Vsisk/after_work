# Function 参数类型加载与归一化增强设计

## What
本次补丁在现有资源主链路上增量增强 function 资源能力，覆盖：
1. `function_loader` / `normalize_functions` 读取并保留参数类型（兼容 `data_type` / `type`）。
2. 对函数返回类型与参数类型执行统一归一化，生成可校验类型引用。
3. 在 `ResourceNormalizer -> ResourceRegistry` 中保留完整函数签名与参数元数据。
4. `ResourceManager` 输出 function candidates 时携带参数类型与返回类型。
5. `PlanValidator` 基于 registry 函数签名执行参数个数、类型可用性与基础类型匹配校验。

## Why
当前 function 参数仅保留参数名，planner/validator 无法判断调用参数是否类型匹配。本次补丁将类型信息作为标准化运行时资源进入环境，避免在 prompt 或运行时临时扫描原始 JSON。

## How
### 1) 类型归一化
新增统一函数 `normalize_function_type(type_value)`，输出标准字段：
- `raw_type`
- `normalized_type`
- `category`
- `is_list`
- `item_type`
- `is_unknown`

支持别名：
- `int/integer/INT -> int`
- `String/string -> string`
- `bool/Boolean -> boolean`
- `long/Long -> long`
- `float/Float -> float`
- `double/Double -> double`
- `List<String>/list[string] -> list[string]`
- 未识别或缺失 -> `unknown`

### 2) function load/normalize
在 `ResourceManager.normalize_functions` 中增强：
- param 读取：`param_name` + `data_type`/`type` + `raw_payload`
- return type 读取：兼容 dict / str
- 记录 `return_type_raw` 与 `normalized_return_type_ref`
- 参数输出标准字段：`param_id/param_type_raw/normalized_param_type/is_list/is_optional/raw_payload`

### 3) registry 结构增强
新增：
- `NormalizedTypeRef`
- `FunctionParamResource`
- `FunctionRegistry(functions_by_id/functions_by_name)`

并将其挂载到 `ResourceRegistry.function_registry`，支持按 id/name 回查完整签名。

### 4) candidate 输出增强
`ResourceManager.format_for_prompt` 中 function candidate 增强为：
- `function_id`
- `function_name`
- `description`
- `normalized_return_type`
- `params[{param_name, param_type, raw_type}]`

### 5) validator 预埋/接入
`PlanValidator` 在函数校验中新增：
- 基于 id/name 回查函数签名（优先 id）
- 参数个数校验
- 参数 expected type 缺失/unknown -> warning
- 实参可推断类型（literal/list/function return）时执行基础匹配

## 兼容性与风险
- 保持旧字段（例如 `params: [name...]`）兼容，不破坏既有主流程。
- 类型未知时不报错中断加载，改为在校验阶段输出 warning。
