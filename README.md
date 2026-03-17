# after-work

这个仓库当前的核心内容是一个 Billing DSL generation agent。它接收用户需求、节点定义和可用资源，输出 DSL 代码以及整条推理链路中的关键中间对象。

## 架构入口

- 架构详解文档：[`AGENT_ARCHITECTURE.md`](/D:/workspace/after_work/AGENT_ARCHITECTURE.md)
- 包导出入口：[`billing_dsl_agent/__init__.py`](/D:/workspace/after_work/billing_dsl_agent/__init__.py)
- 外层 agent service：[`billing_dsl_agent/services/generate_dsl_agent_service.py`](/D:/workspace/after_work/billing_dsl_agent/services/generate_dsl_agent_service.py)
- 核心 orchestrator：[`billing_dsl_agent/services/orchestrator.py`](/D:/workspace/after_work/billing_dsl_agent/services/orchestrator.py)

## 模块分层图

```mermaid
flowchart TB
    subgraph L1["入口层"]
        Caller["Caller / Integrator"]
        Service["GenerateDSLAgentService"]
    end

    subgraph L2["编排层"]
        Orch["CodeAgentOrchestrator"]
    end

    subgraph L3["理解与资源层"]
        LLMParser["LLMRequirementParser"]
        Parser["SimpleRequirementParser"]
        Resolver["DefaultEnvironmentResolver"]
        Matcher["DefaultResourceMatcher"]
        Assembler["PromptAssembler"]
        Client["OpenAIClientAdapter"]
    end

    subgraph L4["规划与生成层"]
        Planner["SimpleValuePlanner"]
        Renderer["DefaultDSLRenderer"]
        Validator["DefaultValidator"]
        Explainer["DefaultExplanationBuilder"]
    end

    subgraph L5["类型与协议层"]
        Types["types/* dataclasses and enums"]
        Protocols["protocols/* interfaces"]
    end

    subgraph L6["配套能力"]
        Normalize["normalize/*"]
        ResourceIndex["resource_index.py"]
        Tests["tests/*"]
    end

    Caller --> Service
    Service --> Orch
    Service -. optional .-> LLMParser
    LLMParser --> Assembler
    LLMParser --> Client
    LLMParser --> Parser
    Orch --> Parser
    Orch --> Resolver
    Orch --> Matcher
    Orch --> Planner
    Orch --> Renderer
    Orch --> Validator
    Orch --> Explainer

    Service --> Types
    Orch --> Protocols
    Parser --> Types
    Resolver --> Types
    Matcher --> Types
    Planner --> Types
    Renderer --> Types
    Validator --> Types
    Explainer --> Types

    Normalize -. supports model normalization .-> Types
    ResourceIndex -. auxiliary lookup helpers .-> Types
    Tests -. verify all layers .-> Service
    Tests -. verify all layers .-> Orch
```

## 主对象流

主链路围绕以下对象展开：

`GenerateDSLRequest -> NodeIntent -> ResolvedEnvironment -> ResourceBinding -> ValuePlan -> GeneratedDSL -> ValidationResult -> GenerateDSLResponse`

其中：

- `GenerateDSLAgentService` 决定是否先走 LLM 需求理解。
- `CodeAgentOrchestrator` 负责执行主 pipeline。
- 后半段生成链路固定为 `resolve -> match -> plan -> render -> validate -> explain`。

更详细的类关系图、时序图和 LLM 分支说明见 [`AGENT_ARCHITECTURE.md`](/D:/workspace/after_work/AGENT_ARCHITECTURE.md)。
