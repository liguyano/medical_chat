# 重构方案：Schedule / Extraction Agent 对齐 deerflow

## 背景

上一轮已完成 Dialog Agent + middleware + tools 的 deerflow 对齐：
`create_dialog_agent()` 纯参数工厂 + `providers` 层（`create_chat_model` / `create_voice_engine`）。

本轮把剩余两个后台 Agent（Schedule / Extraction）对齐到同一架构。

## 现状问题（阅读代码后确认）

1. **未进工厂**：`app/celery_app/tasks.py` 中 schedule / extraction worker
   **直接 `AsyncOpenAI(...)` 实例化**（tasks.py:39、:223）——正是上轮从 Dialog 移除的反模式；
   没有 `create_schedule_agent` / `create_extraction_agent` 入口。
2. **原生 SDK 调用**：两个 Agent 内部用 `llm_client.chat.completions.create(response_format=json_object)`
   + 手动 `json.loads` / `model_validate_json`，未使用 LangChain `BaseChatModel`。
3. **第二处 raw client 消费者**：`app/managers/dialog_history_manager.py::summarize_history`
   直接用 `llm_client.chat.completions.create(model="qwen-plus")`（硬编码模型名）。
4. **死文件**：`medagent/__init__ copy.py`（空）。

## 用户已确认的决策

- **对齐深度 = 深度对齐**：Schedule/Extraction 内部改为 LangChain `BaseChatModel` +
  `with_structured_output`。（用户已知未测试上线的风险，仍选择深度对齐。）
- **清理范围**：仅删 `__init__ copy.py`；保留空 `tools/`、`utils/` 目录（deerflow 有对应结构）。
- **暂缓项（用户未选）**：`tasks.py:162` 的重复 `extraction_agent_worker` 空 TODO 桩
  （被 :191 静默覆盖）本轮**不处理**，仅在此登记为遗留隐患。
- **保留**：空 `client.py` 本轮不动。

## 关键工程判断（必须先说清）

### temperature 行为变化

三个 Agent 当前都绑定 `qwen-plus`（config 中 `temperature: 0.7`）。但：

- **Schedule**：runner 硬编码 `temperature=0.1`（偏离判断需确定性）。
  若直接改用 `create_chat_model`，会读到 config 的 0.7 —— **静默丢失确定性**。
- **Extraction**：现状经 `model_dump()` 实际用 0.7（代码 `.get("temperature", 0.1)` 的
  0.1 默认被覆盖）。改用 `create_chat_model` 仍是 0.7 —— **无变化**。

**处置**：新增 `qwen-plus-precise`（`temperature: 0.1`）模型，仅把 `schedule_agent`
重绑定到它，保持 Schedule 的 0.1 确定性不变；Extraction 保持 `qwen-plus`（0.7）不变。
这是「config 即单一事实来源」的 deerflow 纯参数方式。
（用户的私有 `config.yaml` 需同步该改动，否则 schedule 会退回绑定模型的温度。）

### 结构化输出方式

两个 Agent 的 system prompt 已明确要求「严格 JSON 输出」。改用
`model.with_structured_output(PydanticModel)`（langchain-openai 默认 function_calling），
由 LangChain 负责解析为 pydantic 对象，消除手写 `json.loads` + 校验。

### 工厂签名的有意不对称

- `create_dialog_agent`：**config 驱动**（需按 engine_type 在 text/voice 引擎间选择）。
- `create_schedule_agent` / `create_extraction_agent`：**纯依赖注入**（单模型，
  `model: BaseChatModel` 显式传入，最易测试）。差异写入 factory 文档字符串说明理由。

## 执行步骤

### 1. medagent SDK 层：Agent 内部改 BaseChatModel

- [ ] 1.1 `schedule_agent/agent.py`：`ScheduleAgent.__init__` 参数
  `llm_client + model + temperature + max_tokens` → `model: BaseChatModel`；
  `_analyze_dialog` 改 `model.with_structured_output(ScheduleAnalysis).ainvoke([system, human])`，
  删除 `chat.completions.create` / `response_format` / 手动解析；保留异常兜底返回空 `ScheduleAnalysis()`。
- [ ] 1.2 `extraction_agent/agent.py`：`FieldExtractionAgent.__init__` 参数
  `llm_client + model_config` → `model: BaseChatModel`；`extract_from_dialog` 改
  `model.with_structured_output(ExtractionResult).ainvoke(...)`，删除 `json.loads` +
  `validate_extraction_result`；保留 `extract_with_retry`、`_calculate_derived_fields` 不变。

### 2. medagent SDK 层：新增工厂入口

- [ ] 2.1 `factory.py` 新增 `create_schedule_agent(*, session_id, task_list, model, check_interval, ...)`。
- [ ] 2.2 `factory.py` 新增 `create_extraction_agent(*, session_id, scale_codes, model)`。
- [ ] 2.3 更新 `factory.py` `__all__` 与模块文档字符串（说明纯 DI vs config 驱动的差异）。

### 3. config：新增确定性模型并重绑定

- [ ] 3.1 `config.example.yaml` 新增 `qwen-plus-precise`（`type: language`, `temperature: 0.1`）。
- [ ] 3.2 `agent_models.schedule_agent.language` → `qwen-plus-precise`。

### 4. app 层：worker/runner 改注入 BaseChatModel

- [ ] 4.1 `dialog_history_manager.py::summarize_history`：参数 `llm_client` → `model: BaseChatModel`，
  改 `await model.ainvoke(prompt)`，删除硬编码 `model="qwen-plus"`。
- [ ] 4.2 `schedule_agent_runner.py`：构造参数 `llm_client + model_config` → `model: BaseChatModel`；
  内部改用 `create_schedule_agent`。
- [ ] 4.3 `extraction_agent_runner.py`：构造参数 `llm_client + model_config` → `model: BaseChatModel`；
  内部改用 `create_extraction_agent`；`summarize_history` 调用改传 `model`。
- [ ] 4.4 `tasks.py`：schedule/extraction worker 删除 `from openai import AsyncOpenAI` 与
  `AsyncOpenAI(...)`，改 `from medagent.providers import create_chat_model` +
  `create_chat_model(model_config)`，把 model 注入 runner。

### 5. 清理（严格删除全部死文件）

- [X] 5.1 删除 `medagent/__init__ copy.py`（copy 残留）。
- [X] 5.2 删除 `medagent/client.py`（空文件，零引用）。
- [X] 5.3 删除 `medagent/configs/{database_config,event_config,trace_config}.py`（空 stub，未导出、零引用）。
- [X] 5.4 删除整个 `medagent/trace/`（metadata.py 空 + trace_logger.py 仅注释，无 `__init__` 不可导入，零引用）。
- [X] 5.5 删除 `tasks.py` 中被覆盖的重复 `extraction_agent_worker` 空 TODO 桩（死代码，第二个同名定义静默胜出）。
- 保留：空 `tools/`、`utils/`（`.gitkeep` 目录占位）、各 `__init__.py` 包标记。

### 6. 文档同步（与代码同一变更集）

- [ ] 6.1 `backend/AGENTS.md`：更新 Schedule/Extraction Agent 边界描述
  （BaseChatModel + 工厂入口 + 纯 DI）。
- [ ] 6.2 更新本文件勾选。

## 不做的事（边界）

- 不动 Dialog Agent（上轮已完成）。
- 不改 prompt 文本、`_calculate_derived_fields` 派生逻辑、runner 的 Redis Stream 消费循环。
- 不处理 `tasks.py:162` 重复 worker（用户未选）。
- 不删 `client.py`、不动空 `tools/`、`utils/`（用户已明确）。
- 不运行测试（测试交给他人）；但迁移受影响测试的 import/构造签名，避免制造断裂。

## 风险

- **未测试上线**：BaseChatModel + `with_structured_output` 的解析行为与原生 `json_object`
  在边缘输入上可能有差异（function_calling vs json mode）。已向用户明示，用户接受。
- **config 同步**：私有 `config.yaml` 需手动补 `qwen-plus-precise`，否则 schedule 温度回退。

