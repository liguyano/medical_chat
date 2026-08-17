# 步骤5 - Dialog Agent（对话智能体）开发计划

## 项目信息
- **需求名称**: 入院量表评估 - AI对话方案（Dialog Agent）
- **上游依赖**: 步骤1-4 已完成（基础设施、Redis Stream、状态管理、Schedule Agent）
- **设计来源**:
  - `docs/豆包语音模型集成方案.md`（含完整代码骨架）
  - `docs/后端详细设计方案.md`（AgentLoop、Middleware、错误处理）
  - `docs/需求1-入院量表评估.md`（CICARE 六步规则）
- **开始时间**: 2026-08-17
- **预计工期**: 2-3 天

---

## 一、开发前技术决策（已与用户确认）

| # | 决策项 | 结论 |
|---|-------|------|
| 1 | 代码分层 | **放 medagent 层**（`packages/medagent/agents/service_agent/dialog_agent/`），沿用 schedule_agent 位置 |
| 2 | 语音引擎范围 | **全量实现豆包全双工 WebSocket**（PCM 音频 + 二进制/JSON 协议 + Function Call + 动态约束注入） |
| 3 | 宣教/知情工具 | **定义完整工具 schema + 优雅桩实现**：优先从 `interaction_rule` 表读规则；education/consent ORM（批次B）未落地部分返回结构化占位并标 TODO |
| 4 | Middleware | **搭轻量中间件链**：定义 `before_agent`/`after_agent` hooks + 链式执行器 + 4 个具体中间件 |

### 关键现状说明（务必知晓）
- `packages/medagent/` 框架层（factory/thread_state/providers/middleware）**目前是空壳**，本步骤将首次落地 middleware 链。
- 环境依赖缺失：当前仅装了 `websockets`，**缺 `openai`**。Schedule Agent 已 `import openai` 但未声明依赖，本步骤统一补齐。
- **已知遗留 Bug（不在本步骤修复，归属 test/schedule-agent 分支）**：`schedule_agent/agent.py:152` `from .schedule_agent_prompts import ...` 模块名错误（应为 `.prompts`）。已知会，不动它。

---

## 二、目录结构规划

```
backend/packages/medagent/agents/
├── service_agent/
│   └── dialog_agent/
│       ├── __init__.py             # 导出 DialogAgent / DoubaoVoiceEngine / 工具
│       ├── engine.py               # DialogEngine 抽象 + DoubaoVoiceEngine 实现
│       ├── agent.py                # DialogAgent 核心编排
│       ├── prompt.py               # system_prompt 构建 + CICARE 模板
│       └── tools.py                # 工具 schema 定义 + 执行器（桩）
└── middleware/                     # 轻量中间件链（本步骤首次落地）
    ├── __init__.py
    ├── base.py                     # DialogMiddleware 抽象基类 + MiddlewareChain 执行器
    ├── keyword_intercept.py        # KeywordInterceptMiddleware（字典库拦截）
    ├── schedule_constraint.py      # ScheduleConstraintMiddleware（约束注入）
    ├── event_publish.py            # EventPublishMiddleware（事件发布）
    └── timeout.py                  # TimeoutMiddleware（超时控制）
```

> 说明：豆包引擎放 `dialog_agent/engine.py`（而非设计文档的 `app/engines/`），因决策1定为 medagent 层。引擎不 import app，纯协议实现，符合分层。DialogAgent 编排层需要 `app.managers.*`——沿用 schedule_agent 现状（该现状虽违反"medagent 不 import app"，但用户已明确选择 medagent 层，保持一致）。

---

## 三、开发子步骤

### 5.1 对话引擎抽象层（`engine.py`）
- [ ] 定义 `DialogEngine(ABC)` 抽象基类：`create_session` / `send_input` / `stream_response` / `close_session`
- [ ] 实现 `DoubaoVoiceEngine(DialogEngine)`
  - [ ] WebSocket 连接管理（`wss://.../ws_binary` + Bearer 认证）
  - [ ] `session.create` 会话创建（instructions/voice/tools/audio_format）
  - [ ] `send_input` 音频输入（append + commit，base64 PCM）
  - [ ] `stream_response` 流式解析，归一化为统一事件：`user_transcript|text|audio|tool_call|response_done|error`
  - [ ] `send_tool_result` 工具结果回传（`conversation.item.create`）
  - [ ] `update_session` 动态约束注入（`session.update`）
  - [ ] `close_session` 会话关闭
  - [ ] WebSocket 断线重连（用 `conversation_id` 恢复上下文）
  - [ ] 响应超时保护（30s）
- [ ] 文本降级引擎 `TextChatEngine(DialogEngine)`（基于 AsyncOpenAI，豆包不可用时降级，也便于无 Key 环境验证核心编排逻辑）

### 5.2 核心逻辑实现（`agent.py`）
- [ ] 定义 `DialogAgent` 类：`__init__(session_id, patient_info, task_list, engine, ...)`
- [ ] `handle_patient_input(audio_or_text)` 主循环：驱动 engine.stream_response，分发事件
- [ ] 上下文管理：整合 `AgentStateManager`（Redis 状态）+ `DialogHistoryManager`（PG 持久化），每轮同步更新两者（对应设计"方案B"）
- [ ] 约束提示注入：消费 `ConstraintEvent`，通过 `engine.update_session` 注入下一轮
- [ ] CICARE 规则引导（system_prompt 内嵌，见 5.4）
- [ ] 工具调用处理：`_execute_tool` 分发到 `tools.py`
- [ ] `_notify_backend_agents`：发布 `DialogTurnEvent` 到 `dialog_stream:{session_id}`，供 Schedule/Extraction Agent 消费

### 5.3 Middleware 实现（`middleware/`）
- [ ] `base.py`：`DialogMiddleware` 抽象（`async before_agent(ctx)` / `async after_agent(ctx)`）+ `MiddlewareChain`（顺序执行、异常隔离）
- [ ] `KeywordInterceptMiddleware`：从 `interaction_rule` 表加载规则（桩：表未就绪时用内置最小词表），匹配患者输入，命中则在 ctx 追加约束
- [ ] `ScheduleConstraintMiddleware`：读取 Redis 中 Schedule Agent 发布的约束，注入 system_prompt
- [ ] `EventPublishMiddleware`：after_agent 统一发布 `DialogTurnEvent`/`ToolCallEvent`
- [ ] `TimeoutMiddleware`：调用 `SessionTimeoutManager.update_activity`，检测无响应超时

### 5.4 提示词工程（`prompt.py`）
- [ ] `build_system_prompt(patient_info, task_list)`：内嵌 CICARE 六步 + 沟通风格 + 评估任务 + 工具使用说明
- [ ] CICARE 六步措辞化（Connect/Introduce/Communicate/Ask/Respond/Exit）
- [ ] 追问机制提示（药物过敏→追问具体药物；抽烟→宣教）
- [ ] 从 `dialogue_script` 表加载话术的接口预留（桩：表未就绪用内置模板）

### 5.5 工具定义（`tools.py`）
- [ ] `get_education_material(category, level)` schema + 执行器
  - 桩实现：查 `interaction_rule`/education 表（批次B未落地→返回结构化占位 + TODO）
- [ ] `trigger_consent_form(form_type)` schema + 执行器
  - 桩实现：发布 consent_form 事件到 Redis Stream + 返回占位 form_id
- [ ] `play_audio`（预留，仅 schema）
- [ ] 工具注册表：供 engine.tools 和 `_execute_tool` 共用

### 5.6 Celery 任务封装（`app/celery_app/tasks.py`）
- [ ] 完善 `dialog_agent_preheat`：创建引擎、建立连接、初始化 prompt、注册工具、保存状态到 Redis
- [ ] 对话进程管理与进程绑定逻辑（记录 worker/进程标识到 Redis 状态）

### 5.7 配置与依赖
- [ ] `backend/pyproject.toml` 补依赖：`openai`、`websockets`（已装但需声明）
- [ ] `config.example.yaml` dialog_agent 配置项校验（voice、audio_format 等按需补充）
- [ ] `medagent` 包 `pyproject.toml`（当前为空）按需补充最小元数据

---

## 四、验收标准（本步骤，不含测试执行）

- 对话引擎抽象清晰，DoubaoVoiceEngine 协议实现完整（对齐集成方案文档）
- 文本降级引擎可在无豆包 Key 环境跑通核心编排逻辑
- system_prompt 符合 CICARE 六步规则
- 中间件链可组合、异常隔离、顺序可控
- 工具 schema 完整，桩实现不阻塞主流程
- 每轮对话正确发布 `DialogTurnEvent` 到 Redis Stream（与 Schedule Agent 消费契约一致）
- 约束事件能通过 `update_session` 动态注入
- 代码通过 Ruff 静态检查

> **测试**：按项目约定与用户指令，本步骤**不开发测试**。核心开发完成后编写《步骤5-Dialog-Agent测试计划》文档，测试执行由 `test/*` 分支独立进行。

---

## 五、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 无豆包 API Key，全双工无法联调 | 高 | 提供 `TextChatEngine` 降级引擎验证编排；豆包协议按文档实现并标注"待Key联调" |
| 豆包真实协议与文档骨架有出入 | 中 | 引擎归一化层隔离协议细节；stream_response 输出统一事件，上层不感知 |
| medagent import app 违反分层规则 | 中 | 用户已确认放 medagent 层；与 schedule_agent 现状一致；后续如启用 CI 分层检查再统一治理 |
| education/consent ORM（批次B）未就绪 | 中 | 工具优雅桩，返回结构化占位 + TODO，不阻塞对话 |
| WebSocket 并发/断线 | 中 | 连接池 + conversation_id 重连（本步骤实现基础重连，连接池留 TODO） |

---

## 六、交付物清单

1. `dialog_agent/engine.py`、`agent.py`、`prompt.py`、`tools.py`、`__init__.py`
2. `middleware/base.py` + 4 个具体中间件 + `__init__.py`
3. `app/celery_app/tasks.py` 的 `dialog_agent_preheat` 完善
4. `pyproject.toml` 依赖补齐、`config.example.yaml` 校验
5. `docs/plan/需求1-后端开发计划.md` 步骤5 勾选更新
6. 《步骤5-Dialog-Agent测试计划》文档（开发完成后）

---

**创建时间**: 2026-08-17
**负责人**: AI开发助手
**状态**: 待用户确认 → 确认后建分支 `feat/dialog-agent` 开发
