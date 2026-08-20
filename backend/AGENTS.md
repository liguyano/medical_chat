# AGENTS.md

## 真实模型联调约定

- 文本模型统一使用 `ModelConfig.chat_completion_options()` 构建 Chat Completions 参数。
- 第一阶段 `qwen3.5` 结构化链路使用 `extra_body.enable_thinking=false`，避免推理 token 截断 JSON。
- Dialog 首问和后续问句均由真实语言模型生成；模型失败时发布 `agent_error` SSE 并触发 Celery 重试，禁止静默回退量表原文。
- TextChatEngine 必须跳过供应商发送的 `choices=[]` 用量 chunk。

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

当前 ORM 已落地 30 张表，按领域分组：
- `app/models/staff_account.py` — 医护端登录账号 `staff_account`
- `app/models/patient_task.py` — `patient` / `patient_encounter` / `care_task`
- `app/models/assessment_template.py` — 量表配置 7 表
- `app/models/interaction.py` — AI 对话 6 表
- `app/models/assessment_execution.py` — 评估执行 6 表
- `app/models/quality_review.py` — AI 整体质量评价 4 表
- `app/models/education.py` — 宣教方案、版本与内容单元 3 表
- Alembic 初始迁移：`26533d4669bd_initial_domain_model_batch_a.py`
- 当前迁移头：`20260820_demo_config_center.py`


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
- 第一期文本闭环的 Celery Worker 进程常驻，但 Dialog / Schedule / Extraction Agent 按任务轮次
  按需创建，不在会话上长驻 Redis Stream 消费。Windows `solo` 模式必须按
  `dialog_queue`、`schedule_queue`、`extraction_queue` 各启动一个独立 Worker。
- `POST /api/tasks` 在同一数据库事务内创建 `care_task`、`interaction_session` 和每张量表
  对应的 `assessment_instance`。后台按 `Schedule prepare -> Dialog preheat -> Dialog opening`
  生成并持久化 Task-todo、预热首问；准备期间会话为 `pending`，首问落库后转为 `active`。
- 患者答案进入 PostgreSQL 后，Dialog、Schedule observe、Extraction 必须独立派发。
  Dialog 不得等待另外两个 Agent；Schedule/Extraction 失败由各自 Celery 重试处理。
- 评估完成的唯一事实来源是全部生效量表中 `required=true` 且 `derived=false` 的结构化
  `assessment_answer`。Dialog 禁止按问题下标、消息轮数或 Task-todo 是否问完直接完成任务。
- Extraction 更新结构化进度；进度完整后异步派发 Dialog CICARE Exit，结束语落库后再发布
  `task_status_updated`。
- REST 统一使用 `{code,message,data}`；前端可见的核心 SSE 事件为
  `assistant_text_delta`、`user_transcript_completed`、`extraction_updated`、
  `progress_updated` 和 `task_status_updated`。`dialog_turn` 只供 Agent 内部协作。
- SSE 信封中的 `event_id` 是持久化领域事件编号，用于宣教确认、知情同意和呼叫处理等
  业务关联；`stream_id` 是 Redis Stream 游标，只用于断线续读。SSE 的 `id:` 行继续使用
  Redis Stream ID，禁止用传输游标覆盖领域事件编号。
- Dialog 原生工具结果必须转换为独立业务事件并保存到 `interaction_event`：
  `education_triggered`、`consent_triggered`、`handoff_requested`；通用
  `tool_call` 仅用于内部审计，不得直接推给患者端。模型漏掉关键词规则要求的工具时，
  Dialog Agent 可执行安全兜底工具并要求模型基于真实结果继续回答。
- 宣教材料在患者端保留原文、通俗文本与播报文本三个快照；知情同意条款在对话内确认和
  签名，签名图片保存到 `backend/storage/consent-signatures`，禁止把 data URL 直接写入
  PostgreSQL。患者确认宣教阅读时必须持久化 `education_status_updated` 事件，携带材料编号、
  确认状态和确认时间，供医护端回放恢复。呼叫医护同时写入会话流与
  `nurse_stream:{staff_id}` 全局提醒流。
  呼叫请求必须永久保留在 `interaction_event`：事件 payload 需区分
  `request_source=patient|agent`，Agent 呼叫还需保存 `tool_name`、`tool_args`、
  `tool_result`；护士处理时更新原请求事件的处理状态，并记录处理护士 ID、工号、姓名、
  时间和处理说明，同时发布包含 `request_ids` 的 `handoff_resolved` 事件。历史事件接口
  是患者端和医护监控端刷新恢复呼叫记录的唯一事实来源，不能只依赖实时 Redis Stream。
- `dialog_agent` 在 `agent_models` 中详写绑定两类模型：`language`（OpenAI 兼容文本降级）
  与 `voice`（豆包实时语音，`type: voice`）。豆包真实语音上线前必须用真实 App ID、
  Resource ID、API Key 和匹配事件协议的 endpoint 完成 E2E，禁止以 Fake WebSocket 代替。
- 实时语音一期新增 Qwen Audio/Omni Realtime 并行链路：患者只连接
  `/api/ws/dialog/{session_no}/voice`，后端 `VoiceGateway` 托管供应商 WebSocket；
  语音转写、AI 文本、工具、Schedule/Extraction 结果和音频索引仍写入
  `dialog_stream:{session_id}`，患者端与医护端通过 SSE 断线续读。实时音频帧不写入
  Redis，持久化音频保存为受保护 API 可读取的 WAV 文件；语音模式只派发
  Schedule/Extraction，禁止再次派发文本 Dialog Agent，避免产生重复 AI 问句；
  Extraction 确认结构化进度完整后登记语音完成待处理状态；Voice Gateway 收到最后一轮
  可见 `response.done` 后，二者通过 Redis 完成屏障和幂等锁统一调用完成服务并发布
  `SessionEndEvent`，不再借用文本 Dialog Exit 完成语音会话。Function Calling 的中间
  `response.done` 不得触发任务完成。Gateway 在发布任务结束状态前必须先通过患者
  WebSocket 发送 `response_completed`，作为浏览器等待最后音频排空的顺序屏障。

## 患者端身份边界

- 患者端使用身份证号和手机号核验身份，仅允许存在“在院”住院记录的患者登录。
- 身份证号以加密形式保存，API 不返回身份证号或密文。
- 患者登录会话保存在 Redis，并通过 HttpOnly Cookie 识别当前患者。
- 任务编号只用于任务审计与定位，不作为患者登录凭据。

## 医护端身份边界

- 医护账号保存在 `staff_account`，密码只保存 bcrypt 哈希，不保存明文。
- 医护登录会话保存在 Redis，并通过独立 HttpOnly Cookie `medical_staff_session` 识别。
- 医护端 API 模式必须先调用 `/api/auth/staff/login`；患者 Cookie 不得替代医护会话。
- `seed_demo` 幂等写入多组开发演示医护账号，生产环境不得沿用演示密码。

## 护士 AI 质量评价边界

- `POST/GET /api/rating` 负责单条 AI 消息的逐轮评价，保存 1～5 分、like/dislike、问题标签和自由意见；提交前必须校验消息属于任务会话且角色为 AI。
- `POST /api/quality-reviews` 与 `GET /api/quality-reviews/{task_id}` 负责整次 AI 对话和 AI 评估结果的维度评价。
- 整体评价使用 `quality_review_template`、`quality_review_dimension`、`quality_review`、`quality_review_score`，维度不得硬编码为运行表字段；AI 评估评价的 `target_id` 必须指向 `assessment_submission.id`。

## 结构化答案展示边界

- `assessment_answer_option.option_code_snapshot` 仅用于审计和选项关联，禁止作为患者端或医护端用户可见答案。
- 抽取历史接口和 `extraction_updated` 必须同时返回选项编码、`selected_option_labels`、`selected_option_values` 与统一 `display_value`；页面优先展示量表标签快照，保留可信度和来源消息 ID。
- 任务详情需要返回监控页患者摘要所需的住院号、性别、年龄、入院时间和在院状态，禁止前端使用假数据补齐。
- 医护端登录后的任务列表必须通过 `GET /api/tasks` 按当前 `staff_account.id` 查询 `care_task.assigned_nurse_id`，不能复用患者任务接口或只依赖浏览器本地缓存。

## Demo 系统配置中心

- `/api/system-config` 只允许已登录医护访问，提供宣教材料、交互拦截规则和评估量表的
  查看与直接更新；本 Demo 不建设草稿、审批、发布和操作审计流程。
- 宣教材料使用 `education_program`、`education_program_version`、`education_unit`，
  文本 Dialog 与实时语音工具统一通过 App 层执行器读取当前启用材料并保留事件快照。
- `interaction_rule` 保存后立即生效。为避免 API 与 Celery Worker 的进程内缓存漂移，
  每条患者文本匹配前重新加载当前数据库规则。
- 量表配置接口返回主档、当前版本、分组、题目、选项、规则和护理措施；Demo 编辑只允许
  更新已有记录，必须保持全部 ID 集合和量表内部关联完整。

