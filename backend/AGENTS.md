# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

# 开发规范

1. Python 环境：在 `backend` 下使用 uv 创建环境, 默认采用 python=3.11.

2. 代码大幅重构时不保留旧类名、旧函数、旧配置字段或旧导入路径兼容层, 旧入口直接直接删除, 全部采用新方案.


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

