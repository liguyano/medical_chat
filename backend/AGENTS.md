# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

# 开发规范

1. Python 环境：在 `backend` 下使用 uv 创建环境, 默认采用 python=3.11.

2. 代码大幅重构时不保留旧类名、旧函数、旧配置字段或旧导入路径兼容层, 旧入口直接直接删除, 全部采用新方案.


## 数据库设计事实来源（强制遵守）

**数据库/ORM/迁移的唯一事实来源是以下两份文档，任何表结构、字段命名、关系设计都必须以它们为准：**

- `docs/sql/数据库表业务设计.md` — 核心领域模型
- `docs/sql/出入院宣教与知情同意数据库设计补充.md` — 宣教/知情同意/签名/随访补充域

核心主链路：`patient` → `patient_encounter` → `care_task` → `interaction_session` →
`interaction_message`；评估侧 `care_task` → `assessment_instance` → 多个
`assessment_submission`（AI / 护士 / 最终确认）→ `assessment_answer`
（唯一约束 `(submission_id, question_id)`）。

**已废弃、禁止再使用的旧"8 张核心表"模型**（曾出现在 `docs/后端详细设计方案.md` 早期版本，
及 `backend/app/models/*` 早期 ORM）：`assessment_tasks`、`dialog_sessions`、
`dialog_messages`、`dialog_turns`、`extracted_fields`、`agent_states`、`nurse_ratings`、
`education_records`、`consent_forms`。该单提交模型无法承载人机对比，已作废。

规则：
- 新增/修改 ORM 模型、Alembic 迁移、涉及数据库的代码前，先对照上述两份事实来源文档。
- `docs/后端详细设计方案.md` 的表结构章节仅保留指针，不再作为数据库依据。
- 智能体运行态存 Redis（TTL），不映射为独立 `agent_states` 表。

当前需求1批次 A ORM 已落地 22 张表，按领域分组：
- `app/models/patient_task.py` — `patient` / `patient_encounter` / `care_task`
- `app/models/assessment_template.py` — 量表配置 7 表
- `app/models/interaction.py` — AI 对话 6 表
- `app/models/assessment_execution.py` — 评估执行 6 表
- Alembic 初始迁移：`26533d4669bd_initial_domain_model_batch_a.py`


## 项目架构
```text
medical-evaluate/
├── config.yaml                # Main application configuration
├── extensions_config.json     # MCP servers and skills configuration
├── backend/                   # Backend application (this directory)
│   ├── app/                   # Application layer (import: app.*)
│   │   ├── api/               # FastAPI route modules
│   │   │── configs/           # gateway config info
│   │   │── .../               # ...
│   ├── └── main.py             # FastAPI application
│   ├── packages/
│       ├── pyproject.toml
│       └── medagent/
│           ├── agents/            # LangGraph agent system
│           │   ├── service_agent/ # agent factory(factory + system prompt)
│           │   ├── middlewares/   # middleware components (see Middleware Chain section)
│           │   ├── memory/        # Memory extraction, queue, prompts
│           │   ├── factory.py     # agent抽象声明, agent统一注册工厂
│           │   └── thread_state.py # agent ThreadState schema
│           ├── subagents/         # Subagent delegation system
│           │   ├── builtins/      # general-purpose, bash agents
│           │   ├── executor.py    # Background execution engine
│           │   └── registry.py    # Agent registry
│           ├── tools/builtins/    # Built-in tools (ask_clarification, view_image)
│           ├── mcp/               # MCP integration (tools, cache, client)
│           ├── providers/         # Model providers with thinking/vision support
│           ├── configs/           # Configuration system (app, model, sandbox, tool, etc.)
│           ├── trace/
│           ├── utils/             # Utilities (network, readability)
│           └── client.py          # Embedded Python client
│   ├── tests/                 # Test suite
│   └── docs/                  # Documentation
└── frontend/                   # Next.js frontend application
```

## 代码注释规范

当前注释全部采用中文, 方便快速查阅, 格式如下所示:

```python
def func_name(...) -> ...:
    """函数标题
    作用：描述函数的作用;
    Args:
        - 参数x: ...
        - ...
    Return:
        - 返回值x: ...
        ...
    """
```
- 抽象基类：标明类作用.
- 实现类：写明具体实现类的作用和类参数、类方法等.
- 行内代码：关键步骤的代码,必须写清代码注释.


## App / Agent Split

The backend is split into two layers with a strict dependency direction:

- **Agent** (`packages/medagent/`): Publishable agent framework package (`medagent`). Import prefix: `medagent.*`. Contains agent orchestration, tools, sandbox, models, MCP, skills, config — everything needed to build and run agents.
- **App** (`app/`): Unpublished application code. Import prefix: `app.*`. Contains the FastAPI Gateway API.

**Dependency rule**: App imports medagent, but medagent never imports app.

**Import conventions**:
```python
# Agent internal
from medagent.agents import make_lead_agent
from medagent.configs import AgentConfig

# App internal
from app.configs.app_config import get_app_config

# App → Agent (allowed)
from medagent.configs.agent_config import get_agent_config

# Agent → App (FORBIDDEN)
# from app.configs.app_config import ...  # ← will fail CI
```

## Schedule Agent 边界

- SDK 核心位于
  `packages/medagent/agents/service_agent/schedule_agent/`，包含问题任务模型、
  提示词、LLM 语义检查、进度状态和工具完整性检查；该目录禁止导入 `app.*`。
- 应用编排位于 `app/workers/schedule_agent_runner.py`，负责读取 PostgreSQL
  对话历史、消费 Redis Stream、保存 Redis 检查点以及发布约束/结束事件。
- 独立 Celery worker 通过 `app/celery_app/runtime.py` 按进程初始化数据库与
  Redis；`worker_process_init` 负责 prefork 初始化，Schedule Agent 任务入口
  额外执行幂等兜底，以兼容 Windows solo worker。
- `app/managers/assessment_loader.py` 只加载“当前生效且已发布”的量表版本，
  并将 ORM 数据转换为 `medagent` 的 `QuestionTask`。
- `app/managers/assessment_catalog_importer.py` 幂等导入
  `docs/structured/assessment-scales`。源文件为 `pending_review` 时必须保持“审核中”，
  临床审核前禁止直接发布。
- 所有模型（语言 + 语音）统一登记在 `config.yaml` 的 `models` 列表，用 `type: language|voice`
  区分类别；`agent_models` 绑定支持简写（`agent: model_name` → 语言模型）或详写
  （`agent: {language: .., voice: ..}`）。Schedule Agent 通过
  `get_agent_model_config("schedule_agent")` 取语言模型。

## Dialog Agent 边界

- SDK 核心位于
  `packages/medagent/agents/service_agent/dialog_agent/`，中间件位于
  `packages/medagent/agents/middlewares/`；两者只依赖 `medagent.*` 协议与类型，
  禁止导入 `app.*`。
- 中间件目录命名对齐 deerflow（`middlewares/`），但因 Dialog Agent 使用自定义
  `DialogEngine`（语音全双工 WebSocket / 文本双引擎），**不经过 LangGraph `create_agent`
  模型节点**，故采用**对话轮次级**钩子 `before_agent(context)` / `after_agent(context, output)`，
  有意区别于 LangChain `AgentMiddleware` 的 `before_model`/`after_model`（后者操作
  LangGraph state，语音场景不适用），不套用其命名以免语义误导。
- Dialog 工具（`dialog_agent/tools.py`）用 LangChain `@tool` 定义，函数签名即 schema
  单一来源；引擎侧所需 OpenAI function dict 经 `build_openai_tool_schemas()`
  （`convert_to_openai_tool`）生成，对外仍导出 `DIALOG_TOOLS`（dict 列表）与
  `execute_tool(name, args)`（注册表查表 + `ainvoke`，无手写 if/elif 路由）。
- 引擎装配统一走 SDK 工厂 `medagent.agents.factory.create_dialog_agent`：按 `engine_type`
  （`text`/`doubao`）从 `agent_models` 解析绑定，文本路径构造 `TextChatEngine`，语音路径经
  `medagent.providers.create_voice_engine` 构造 `DoubaoVoiceEngine`。工厂遵循纯参数设计，
  引擎实例化不再散落在 app 层。
- 应用适配与依赖组装位于 `app/workers/dialog_agent_runtime.py`，`get_runtime_dependencies`
  返回 middlewares / state_store / history_store / tool_executor，注入 PostgreSQL 历史、
  Redis 状态、Schedule 约束源、事件接收器和活动时间更新器，供工厂消费。
- Schedule 与 Dialog 共用 `dialog_stream:{session_id}`。Dialog 通过持久化
  `dialog_agent:constraint_cursor:{session_id}` 只消费一次 `ConstraintEvent`，
  并发布扁平的 `DialogTurnEvent` / `ToolCallEvent`。
- `DialogEngine` 统一语音与文本事件。文本引擎回传工具结果后必须继续调用模型，
  直到生成患者可见回复或达到最大工具轮次；供应商错误不得直接暴露给患者。
- 独立 Celery worker 的 `dialog_agent_preheat` 必须先调用
  `ensure_worker_runtime()`，再加载 PostgreSQL 量表并通过 App 适配层组装智能体。
- `dialog_agent` 在 `agent_models` 中详写绑定两类模型：`language`（OpenAI 兼容文本降级）
  与 `voice`（豆包实时语音，`type: voice`）。豆包真实语音上线前必须用真实 App ID、
  Resource ID、API Key 和匹配事件协议的 endpoint 完成 E2E，禁止以 Fake WebSocket 代替。

