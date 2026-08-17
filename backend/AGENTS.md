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

