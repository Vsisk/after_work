# End-to-End Demo

使用仓库内置的虚拟资源跑一遍完整 DSL 生成链路：

```powershell
.\.venv\Scripts\python run_demo_e2e.py --mode stub --pretty
```

`stub` 模式会走完整的 `resource loader -> normalize -> environment filter -> semantic select -> plan -> validate -> render` 链路，但 LLM 响应由内置 demo client 提供，适合稳定回归。

如果本地已经配置好以下环境变量，也可以切换到真实 LLM：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

运行命令：

```powershell
.\.venv\Scripts\python run_demo_e2e.py --mode openai --pretty
```

虚拟资源定义文件在 [billing_dsl_agent/demo_virtual_resources.json](/D:/workspace/after_work/billing_dsl_agent/demo_virtual_resources.json)。

常用参数：

```powershell
.\.venv\Scripts\python run_demo_e2e.py --mode stub --requirement "generate title from customer gender" --node-path "invoice.customer.title" --node-name "title" --pretty
```
