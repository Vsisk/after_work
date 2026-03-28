# namingSQL 参数签名增强开发计划

## Phase #1 基线改造（Loader + Normalizer + Registry）

### Task #1 扩展 BO namingSQL 归一化数据结构
- 内容：新增 namingSQL 标准签名 dataclass，并扩展 BOResource 的签名索引字段。
- 预期结果：运行时对象可完整承载 namingSQL 参数类型签名。
- 状态：Finished

### Task #2 修改 BO loader 读取完整 param_list 类型定义
- 内容：完整读取 `param_name/data_type/data_type_name/is_list/raw_payload`。
- 预期结果：load 后不再丢失 namingSQL 参数类型信息。
- 状态：Finished

### Task #3 修改 ResourceNormalizer 建立 namingSQL 签名索引
- 内容：生成 normalized namingSQL def、param、type_ref、signature_display 与 by-key 索引。
- 预期结果：可通过 bo_id / naming_sql_id 回查签名与参数元信息。
- 状态：Finished

## Phase #2 消费链路改造（Candidate + Validator）

### Task #4 增强 ResourceManager BO candidate 输出
- 内容：在保留 `naming_sqls` 的同时输出 `naming_sql_defs` 与 params 类型签名。
- 预期结果：planner 可直接看到 namingSQL 参数签名。
- 状态：Finished

### Task #5 接入 namingSQL 参数签名校验
- 内容：新增 `compare_namingsql_param_type` 及匹配结果对象；在 validator 中接入参数个数/签名存在性/顺序化类型比对。
- 预期结果：validator 能输出可解释的 mismatch/warning，且接口可扩展。
- 状态：Finished

## Phase #3 测试与交付

### Task #6 补充单元测试
- 内容：覆盖 loader/normalize/registry/candidate/validator/compare 函数关键场景。
- 预期结果：核心分支具备可回归测试。
- 状态：Finished

### Task #7 执行测试、更新进度并提交
- 内容：执行 pytest（必要时按模块执行），追加 progress 记录，完成 git commit 与 PR 文本。
- 预期结果：改造可验证、可审计、可追踪。
- 状态：Finished
