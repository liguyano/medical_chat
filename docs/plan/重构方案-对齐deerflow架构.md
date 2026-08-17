# 重构方案：对齐 DeerFlow 架构（修订版）

> **修订说明（2026-08-17）**：原方案主张「删除 `engine.py`，全部改用 LangGraph `create_agent`」，
> 经核实 **该前提是错误的**：豆包是端到端实时语音**全双工 WebSocket** 模型，交互是持续双向事件流
> （`session.update` 动态约束 / 实时打断 / `response.audio.delta` 音频流），
> **无法适配 `BaseChatModel` 的回合式 `invoke/stream` 语义**（见 `engine.py:5-7`、
> AGENTS.md「Dialog Agent 边界」、`docs/豆包语音模型集成方案.md`）。
> 若照原方案删引擎，**语音主链路直接报废**，只剩文本降级路径可用，与需求（语音优先）冲突。
>
> 因此本轮**保留 `DialogEngine` 双引擎抽象**，仅在 **middleware 结构/命名** 与 **tools 结构** 上向
> deerflow 靠拢。已与人类确认方向（保留双引擎；范围 = Dialog Agent + middleware 命名对齐 +
> tools 结构对齐；Schedule / Extraction 本轮不动）。

## 一、现状核实结论

### 1.1 三个 Service Agent 的真实性质

| Agent | 现状实现 | 能否套 `create_agent` | 本轮处理 |
|---|---|---|---|
| **Dialog** | 自定义 `DialogAgent` 回合编排，统一语音 WS / 文本两引擎 | ❌ 语音路径不是 `BaseChatModel` | 保留编排，对齐 middleware/tools |
| **Schedule** | 纯后台「监督器」`ScheduleAgent`：定期 LLM 判偏离 + 工具完整性检查，**从不直接对话** | ❌ 它是 evaluator，非对话 agent | 本轮不动 |
| **Extraction** | 字段抽取，结构化输出 | ⚠️ 理论可适配，收益低 | 本轮不动 |

**结论**：deerflow 的 `create_agent`（文本 LLM + 工具循环）模式，本项目三个 agent **无一契合**。
值得学习的是 deerflow 的**设计原则**（纯参数工厂、SDK/App 分层、中间件标准化命名、工具单一来源），
而非 `create_agent` 这一具体 API。

### 1.2 deerflow 中间件真实 API（供对齐参考，非照搬）

LangChain `AgentMiddleware[State]` 的钩子（每个均有 `a` 前缀异步孪生）：

```python
def before_model(self, state, runtime: Runtime) -> dict | None: ...
def after_model(self, state, runtime: Runtime) -> dict | None: ...
def wrap_model_call(self, request: ModelRequest, handler) -> ModelCallResult: ...
def wrap_tool_call(self, request: ToolCallRequest, handler) -> ToolMessage | Command: ...
```

**关键**：这些钩子操作 **LangGraph state + 模型节点**。我们的语音路径是 WebSocket 事件流，
**不经过 LangGraph 模型节点**，拿不到 `state` / `runtime`。故**不能照搬签名**，
只做命名/结构对齐，保留回合级 `context` 字典语义。

## 二、本轮重构范围（三项）

### 阶段 A：tools 结构对齐（真价值，优先）

**现状问题**（`service_agent/dialog_agent/tools.py`）：
- 工具用裸 `dict` schema（`TOOL_GET_EDUCATION_MATERIAL` 等）手写 OpenAI function 格式；
- `execute_tool` 用 `if/elif` 手写路由；
- schema 与实现分离，存在**漂移风险**（改了函数签名忘改 schema）。

**对齐方案（仿 deerflow `tools/builtins` 的 LangChain `@tool`）**：
- 用 `langchain_core.tools.tool` 装饰器定义工具：**函数签名即 schema 单一来源**；
- 引擎侧仍需 OpenAI dict：新增 `build_openai_tool_schemas()`，用
  `langchain_core.utils.function_calling.convert_to_openai_tool` 从 `@tool` 生成 dict；
- 执行改为**工具注册表查表 + `ainvoke`**，删除手写 `if/elif` 路由；
- 保持 `DIALOG_TOOLS`（供引擎的 OpenAI dict 列表）与 `execute_tool(name, args)`（供
  `DialogAgent._handle_tool_call` 的执行入口）两个对外名字不变，内部实现替换，**避免波及编排层与引擎**。

**落点文件**：`service_agent/dialog_agent/tools.py`（重写）。

### 阶段 B：middleware 结构对齐（低价值，谨慎）

**对齐动作**：
- 目录 `agents/middleware/` → `agents/middlewares/`（deerflow 用复数）；
- `__init__.py`、`base.py` 内注释与文档说明**明确标注**：本项目 Dialog Agent 用自定义
  `DialogEngine`（非 `create_agent`），故中间件采用**回合级** `before_agent(context)` /
  `after_agent(context, output)` 钩子，**有意区别于** LangChain 的 `before_model/after_model`
  （后者操作 LangGraph state，语音全双工不适用）；
- **不改钩子名**（改成 `before_model` 会误导语义）。

**落点文件**：`middleware/` 整目录改名为 `middlewares/`；同步修正所有 import：
`agents/factory.py`、`app/workers/dialog_agent_runtime.py`、`app/celery_app/tasks.py`、
`agents/service_agent/dialog_agent/agent.py`（`from ...middleware.base` → `...middlewares.base`）。

> **遵守 AGENTS.md 规范 #2**：大幅重构不保留旧导入路径兼容层，`middleware/` 目录直接删除。

### 阶段 C：Dialog Agent 编排保留

- `DialogAgent` / `DialogEngine` / `DoubaoVoiceEngine` / `TextChatEngine` **全部保留**；
- 仅因阶段 A/B 调整内部 import，不改编排逻辑与引擎协议。

## 三、执行步骤

- [X] A1. 重写 `tools.py`：`@tool` 定义 + `build_openai_tool_schemas()` + 注册表执行；保持 `DIALOG_TOOLS` / `execute_tool` 对外名。
- [X] B1. `git mv` 目录 `middleware/` → `middlewares/`。
- [X] B2. 修正 `base.py` / `__init__.py` 注释，标注回合级钩子与 LangChain 的差异。
- [X] B3. 修正全部 import：factory / dialog_agent_runtime / tasks / agent.py。
- [X] C1. 核对 `DialogAgent` 编排与引擎无破坏。
- [X] D1. 更新 `backend/AGENTS.md`（Dialog Agent 边界：tools 采用 LangChain `@tool` + 引擎 dict 转换；middlewares 目录与回合级钩子说明）。
- [X] D2. 更新受影响测试文件的 import（`middleware`→`middlewares` 路径），**不运行测试**（按人类要求）。

## 四、不做的事（明确边界）

- ❌ 不删 `engine.py` / 不改 `create_agent`（语音全双工硬约束）。
- ❌ 不把 `before_agent/after_agent` 改名为 `before_model/after_model`（语义误导）。
- ❌ 不动 Schedule Agent / Extraction Agent（非对话 agent，本轮范围外）。
- ❌ 不运行测试（按人类要求，仅保证 import 一致、不制造断裂）。

## 五、关键原则

1. **技术栈约定的正确理解**：AGENTS.md 要求用 LangChain/LangGraph，但语音全双工是其能力边界外的
   场景；此处以 `DialogEngine` 抽象承接，属合理工程取舍，非「造轮子」。
2. **对齐 deerflow 的原则而非 API**：纯参数工厂（已完成）、SDK/App 分层（已完成、CI 强制）、
   工具单一来源（本轮 A）、中间件命名规范（本轮 B）。
3. **无兼容层**：旧导入路径直接删除（AGENTS.md #2）。
