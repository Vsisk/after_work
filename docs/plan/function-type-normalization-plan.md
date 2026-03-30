# Function 参数类型补丁开发计划

## Phase #1 资源模型与归一化
- Task #1（Finished）扩展 `models.py` 函数资源模型，加入 `NormalizedTypeRef`、`FunctionParamResource`、`FunctionRegistry`。
- Task #2（Finished）增强 `resource_manager.py` 的 function normalize，读取 `data_type/type` 并归一化返回值和参数类型。
- Task #3（Finished）增强 `resource_normalizer.py`，将参数类型、签名展示与 source/raw metadata 写入 `ResourceRegistry`。

## Phase #2 候选输出与校验增强
- Task #1（Finished）增强 `resource_models.py` 与 `resource_manager.py` 的 function candidate 输出结构，携带参数类型和返回类型。
- Task #2（Finished）增强 `plan_validator.py` 函数签名校验（参数个数 + unknown warning + 基础类型匹配）。

## Phase #3 测试与验证
- Task #1（Finished）补充 `test_resource_manager.py` 覆盖 data_type/type/list/unknown/return type 归一化。
- Task #2（Finished）新增 `test_function_signature_validation.py` 覆盖函数签名回查、参数个数与类型校验、unknown warning。
- Task #3（Finished）更新 `test_agent_main_flow.py`，校验 function registry 与无参函数 normalize。
- Task #4（Finished）执行语法检查 `py_compile`；`pytest` 受环境 pydantic/typing 兼容性限制未能完成。
