# BO namingSQL 参数签名增强设计

## 需求澄清结论

基于当前需求说明，已明确以下边界并作为本次实现范围：

1. 本次为 **增量增强**，复用现有 BO loader / normalizer / registry / validator 主链路，不重写系统。
2. namingSQL 参数类型签名以 `data_type -> data_type_name -> is_list` 为固定匹配顺序。
3. 缺失类型信息时不能中断加载，需在标准化结果中保留 unknown/partial 状态，并在 validator 输出 warning/note。
4. 本次 validator 至少完成：
   - namingSQL 可解析性
   - 签名存在性
   - 参数个数/参数名校验
   - 具备可复用的类型比较接口，支持后续完整实参类型推导接入。
5. ResourceManager 的 BO candidate 需要把 namingSQL 参数签名透出给 planner。

## WHAT

对 BO namingSQL 资源做“可校验签名化”增强：

- load：完整读取 `param_list` 中参数类型定义；
- normalize：生成稳定、可索引的 namingSQL 与参数标准结构；
- registry：支持通过 `bo_id / naming_sql_id` 回查完整签名；
- candidate：向 planner 透出 namingSQL 参数签名；
- validator：接入 namingSQL 参数签名校验与类型比较框架。

## WHY

当前链路虽然能识别 namingSQL 名称与参数名，但不能判断参数类型是否匹配，导致：

- planner 看不到真实签名，生成参数方案不稳定；
- validator 只能做存在性校验，无法做类型一致性约束；
- 缺失类型信息时无显式告警，不利于后续补数与诊断。

## HOW

### 1) 数据结构扩展（bo_models / models）

新增 namingSQL 归一化模型：

- `NormalizedNamingTypeRef`
- `NormalizedNamingSQLParam`
- `NormalizedNamingSQLDef`

并在 `BOResource` 中新增 namingSQL 参数签名索引字段（按 id/name/key 回查）。

### 2) BO loader 改造

在 `_normalize_params` 中完整读取：

- `param_name`
- `data_type`
- `data_type_name`
- `is_list`
- `raw payload`

保证原始结构可追溯，不因字段缺失崩溃。

### 3) ResourceNormalizer 改造

在 `_normalize_bos` 中：

- 构建每个 namingSQL 的标准化定义；
- 产出 `signature_display`；
- 建立 `naming_sql_signature_by_key` 与 `naming_sql_param_meta_by_key` 索引。

### 4) ResourceManager candidate 输出增强

保持 `naming_sqls` 兼容字段，同时新增结构化 `naming_sql_defs`，每项包含：

- `naming_sql_id`
- `naming_sql_name`
- `signature_display`
- `params[{param_name,data_type,data_type_name,is_list}]`

### 5) PlanValidator 接入

新增独立比较函数：

- `compare_namingsql_param_type(expected, actual) -> NamingSQLParamTypeMatchResult`

比较顺序：

1. `data_type`
2. `data_type_name`
3. `is_list`

并在 fetch/fetch_one 语义校验中加入：

- 参数个数与名称校验；
- expected 签名字段存在性校验（缺失给 warning）；
- 若 actual 具备类型信息，则执行顺序化比较并输出 mismatch reason；
- 若 actual 类型暂不可得，保留 warning + 可扩展接口。

## 影响范围

- `billing_dsl_agent/bo_models.py`
- `billing_dsl_agent/bo_loader.py`
- `billing_dsl_agent/models.py`
- `billing_dsl_agent/resource_normalizer.py`
- `billing_dsl_agent/resource_manager.py`
- `billing_dsl_agent/plan_validator.py`
- `billing_dsl_agent/tests/*`（新增/调整对应单测）

## 兼容性

- 保留原 `naming_sqls: List[str]`，避免 prompt 侧破坏；
- 新签名字段以增量方式加入，不影响既有主流程路径。

## 测试设计

覆盖：

1. loader 能读取 namingSQL param 的完整类型信息；
2. normalize 后签名完整保留，含 unknown 标记；
3. registry 可通过 naming_sql_id 回查签名；
4. candidate 输出带 namingSQL 参数签名；
5. `compare_namingsql_param_type` 四种匹配/不匹配分支；
6. expected 缺失类型字段不崩溃且给 warning；
7. validator 校验参数个数与签名存在性；
8. 当 actual 类型可用时按 `data_type -> data_type_name -> is_list` 顺序给出结果。
