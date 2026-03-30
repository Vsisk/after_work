# BO namingSQL 参数类型签名增强设计

## WHAT
- 增量增强 BO loader/normalizer/validator：将 namingSQL `param_list` 的 `data_type/data_type_name/is_list` 完整纳入运行时资源。
- 在 BO registry 中以 `naming_sql_id` 级别可回查参数签名。
- 在 ResourceManager 的 BO candidate 输出中携带 namingSQL 参数签名。
- 新增独立比较逻辑 `compare_namingsql_param_type`，严格按 `data_type -> data_type_name -> is_list` 顺序比较。

## WHY
- 现状只能校验 namingSQL 存在与参数名/个数，无法做参数类型合法性校验。
- 参数签名进入标准资源后，planner 可见、validator 可查，后续可持续扩展 actual 类型推导。

## HOW
1. `bo_loader.py`：保留 namingSQL/param 原始 payload，确保类型字段可追溯读取。
2. `models.py`：新增
   - `NormalizedNamingTypeRef`
   - `NormalizedNamingSQLParam`
   - `NormalizedNamingSQLDef`
   并扩展 `BOResource`：`naming_sqls` / `naming_sqls_by_id` / `naming_sql_signatures_by_key`。
3. `resource_normalizer.py`：将 BO namingSQL 归一化到上述模型并建立索引。
4. `resource_manager.py`：BO candidate 的 `naming_sqls` 输出升级为对象列表，包含参数签名。
5. `plan_validator.py`：
   - namingSQL 解析支持唯一性判定（无匹配报 `unknown_naming_sql`，多匹配报 `ambiguous_naming_sql`）；
   - 校验参数名/个数；
   - 校验 expected 签名字段存在性（缺失给 warning）；
   - 若 actual 可推导，调用 `compare_namingsql_param_type` 做顺序比较。

## 澄清结论
- 仅 namingSQL 不存在为 error；expected 签名缺失为 warning。
- BO candidate 不保留旧字符串列表，仅保留结构化 namingSQL 信息。
- 仅改 BO 资源内部管理与校验逻辑，不改变外部主流程接口语义。
