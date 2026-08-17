# API 接口对接文档

> 面向前端（Next.js）的后端接口契约。所有 REST 接口统一返回 `{code, message, data}`；
> AI 回复与进度不走 REST 同步返回，一律经 **SSE** 事件流异步回推。
>
> - 版本：`0.1.0`
> - Base URL：`http://<host>:<port>`（开发期 CORS 全放开）
> - 编码：UTF-8
> - 健康检查：`GET /health` → `{"status": "ok"}`

---

## 1. 统一响应结构

所有 REST 接口（SSE 除外）返回体：

```jsonc
{
  "code": "OK",          // 业务错误码，成功恒为 "OK"
  "message": "成功",      // 人类可读提示
  "data": { }            // 业务数据载荷，失败时可能为 null
}
```

- 前端**以 `code` 判定成败**，不要仅依赖 HTTP 状态码。
- 失败时 `code` 为 `ERR_*`，`message` 为中文提示，HTTP 状态码见错误码表。

---

## 2. 评估任务接口 `/api/tasks`

### 2.1 创建评估任务

`POST /api/tasks`

请求体（`CreateTaskRequest`）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `patient_id` | int | 是 | — | 患者 ID |
| `encounter_id` | int | 是 | — | 住院记录 ID |
| `task_type` | string | 否 | `assessment` | 任务类型 |
| `task_name` | string | 否 | `入院量表评估` | 任务名称 |
| `task_source` | string | 否 | `manual` | 任务来源 |
| `collection_mode` | string | 否 | `ai_dialogue` | 采集模式：`traditional_form` \| `ai_dialogue` |
| `assigned_nurse_id` | int \| null | 否 | null | 负责护士 ID |
| `planned_start_time` | datetime \| null | 否 | null | 计划开始时间（ISO 8601） |

响应 `data`（`TaskResponse`）：

```jsonc
{
  "task_no": "TASK-xxxx",
  "patient_id": 1,
  "encounter_id": 10,
  "task_type": "assessment",
  "task_name": "入院量表评估",
  "task_source": "manual",
  "collection_mode": "ai_dialogue",
  "task_status": "pending",
  "assigned_nurse_id": null,
  "created_at": "2026-08-17T09:00:00Z"
}
```

### 2.2 获取任务详情

`GET /api/tasks/{task_no}`

- 路径参数 `task_no`：任务编号。
- 响应 `data` 同 `TaskResponse`。
- 任务不存在 → `ERR_TASK_003`（404）。

---

## 3. 对话交互接口 `/api/dialog`

> 交互协议：REST 只做**落库 + 发布事件**，AI 回复由 Dialog Agent 异步产出，经 SSE 回推。
> 发送消息接口**不会**同步返回 AI 回复。

### 3.1 开始对话

`POST /api/dialog/start`

请求体（`StartDialogRequest`）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `task_no` | string | 是 | — | 关联评估任务编号；任务须为 `ai_dialogue` 采集模式 |
| `scale_codes` | string[] | 否 | `[]` | 本次对话涉及的量表编码列表 |
| `channel_type` | string | 否 | `text` | 渠道类型：`text` \| `voice` |
| `engine_type` | string | 否 | `text` | 对话引擎：`text`（文本降级）\| `doubao`（实时语音） |

响应 `data`（`DialogResponse`）：

```jsonc
{
  "session_no": "SESS-xxxx",
  "task_no": "TASK-xxxx",
  "session_status": "active",
  "started_at": "2026-08-17T09:01:00Z"
}
```

- 副作用：投递 `dialog_agent_preheat` 预热任务（失败不阻断会话创建）。
- 任务不存在或采集模式非 AI 对话 → `ERR_DIALOG_004`（404）。

**前端时序**：调用 `start` 拿到 `session_no` 后，**立即** `GET /api/sse/dialog/{session_no}`
建立 SSE 连接，再开始发送消息，避免漏收早期事件。

### 3.2 发送患者消息

`POST /api/dialog/{session_no}/message`

请求体（`SendMessageRequest`）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `content_text` | string \| null | 二选一 | null | 患者文本内容 |
| `audio_base64` | string \| null | 二选一 | null | Base64 音频（与文本不可同时为空） |
| `audio_format` | string | 否 | `pcm` | 音频格式：`pcm` \| `opus` \| `mp3` |
| `message_type` | string | 否 | `text` | 消息类型：`text` \| `audio` |

响应 `data`（`SendMessageResponse`）：

```jsonc
{
  "session_no": "SESS-xxxx",
  "message_no": "MSG-xxxx",
  "turn_no": 3,
  "intercepted": false      // 是否命中关键词约束（命中会追加约束事件）
}
```

- 同一会话加 Redis 锁防并发（TTL 30s）；并发冲突 → `ERR_DIALOG_003`（409）。
- 文本与音频同时为空 → `ERR_COMMON_001`（422）。
- 会话不存在 → `ERR_DIALOG_001`（404）；会话非 `active` → `ERR_DIALOG_002`（409）。
- **AI 回复不在此返回**，请在 SSE 流上监听 `dialog_message` 事件。

### 3.3 获取对话历史

`GET /api/dialog/{session_no}/history`

响应 `data`（`DialogHistoryResponse`）：

```jsonc
{
  "session_no": "SESS-xxxx",
  "total": 6,
  "messages": [
    {
      "message_no": "MSG-xxxx",
      "turn_no": 1,
      "role_type": "患者",       // 患者 | AI | 护士 ...
      "message_type": "text",
      "content_text": "我不吸烟",
      "occurred_at": "2026-08-17T09:02:00Z"
    }
  ]
}
```

- 会话不存在 → `ERR_DIALOG_001`（404）。

---

## 4. SSE 事件流接口 `/api/sse`

基于 `text/event-stream`。支持 **`Last-Event-ID` 头**断线续读，服务端 30s 无消息发送 `ping` 心跳。

### 4.1 患者端订阅

`GET /api/sse/dialog/{session_no}`

### 4.2 医护端只读监听

`GET /api/sse/monitor/{session_no}`

> 二者当前均消费 `dialog_stream:{session_no}`（单会话）。多会话聚合监听后续补充。
> 会话不存在 → `ERR_SSE_001`（404）。

### 4.3 SSE 帧格式

```
event: dialog_message
id: 1699999999999-0
data: {"event_type":"dialog_turn","turn_number":3,"question":"...","answer":"..."}
```

- `id` 为 Redis Stream 消息 ID，断线重连时通过 `Last-Event-ID` 头带回。
- `data` 为 JSON 字符串（`ensure_ascii=false`，UTF-8 中文原文）。

### 4.4 SSE 事件名与业务事件映射

服务端把内部业务事件归并为 **3 类 SSE `event` 名**：

| SSE `event` | 触发来源（`event_type`） | 用途 |
|-------------|--------------------------|------|
| `dialog_message` | `dialog_turn` / `dialog_text` / `dialog_audio` | AI 回复 / 流式文本 / 音频 |
| `progress_update` | `tool_call` / `constraint` / `session_start` / `session_end` / `extraction_result` | 进度、约束提示、工具调用、抽取结果 |
| `ping` | —（心跳） | 保活，`data` 为空 |
| `error` | —（读流异常） | `data: {"message": "事件流读取失败"}` |

### 4.5 业务事件 `data` 载荷字段

所有事件都含基类字段：`event_id`、`event_type`、`session_id`、`timestamp`、`version`。各类型附加字段：

| `event_type` | 附加字段 |
|--------------|----------|
| `dialog_turn` | `turn_number`, `question`, `answer`, `tool_calls?`, `metadata?` |
| `dialog_text` | `turn_number`, `text_chunk`, `is_final` |
| `dialog_audio` | `turn_number`, `audio_url`, `audio_format`, `duration_ms?` |
| `tool_call` | `turn_number`, `tool_name`, `tool_args`, `tool_result?` |
| `constraint` | `constraint_type`(deviation\|missing_tool\|timeout\|keyword_hit), `constraint_prompt`, `remaining_tasks[]` |
| `session_start` | `patient_id`, `task_id`, `form_ids[]` |
| `session_end` | `end_reason`(completed\|timeout\|nurse_intervention), `total_turns`, `duration_seconds` |
| `extraction_result` | `form_id?`, `extracted_fields{}`, `confidence_scores{}` |

---

## 5. 错误码表

| `code` | HTTP | 含义 |
|--------|------|------|
| `OK` | 200 | 成功 |
| `ERR_COMMON_001` | 422 | 请求参数校验失败 |
| `ERR_COMMON_002` | 404 | 资源不存在 |
| `ERR_COMMON_003` | 409 | 资源状态冲突 |
| `ERR_COMMON_500` | 500 | 服务器内部错误 |
| `ERR_TASK_001` | 404 | 患者不存在 |
| `ERR_TASK_002` | 404 | 住院记录不存在 |
| `ERR_TASK_003` | 404 | 评估任务不存在 |
| `ERR_DIALOG_001` | 404 | 交互会话不存在 |
| `ERR_DIALOG_002` | 409 | 会话当前状态不允许该操作 |
| `ERR_DIALOG_003` | 409 | 会话正在处理其他消息，请稍后重试 |
| `ERR_DIALOG_004` | 404 | 关联任务不存在或不可进行对话 |
| `ERR_SSE_001` | 404 | 会话事件流不存在 |
| `ERR_KEYWORD_001` | 500 | 关键词规则加载失败 |

---

## 6. 前端端到端对接时序（AI 对话采集）

```
1) POST /api/tasks                      → 得到 task_no
2) POST /api/dialog/start {task_no}     → 得到 session_no（后台投递 preheat 预热）
3) GET  /api/sse/dialog/{session_no}    → 建立 SSE 长连接（立即建立，先于发消息）
4) POST /api/dialog/{session_no}/message→ 患者输入落库并发布事件（同步返回仅 message_no/turn_no）
5) SSE  event: dialog_message           → 接收 AI 回复
   SSE  event: progress_update          → 接收进度 / 约束 / 抽取结果
   SSE  event: session_end              → 评估结束，可断开连接
6) GET  /api/dialog/{session_no}/history→ 需要时拉取完整历史
```

> **对接注意**：第 4 步是「发射后不管」，AI 回复只在第 5 步的 SSE 流里出现；
> 前端不要等待第 4 步的响应体拿回复。

---

## 7. 当前实现边界（对接前须知）

- REST 三组路由（tasks / dialog / sse）、统一响应、错误码、关键词拦截、SSE 续读与心跳
  **均已就绪**，可直接对接。
- Schedule / Extraction Agent 已完成 `BaseChatModel` 依赖注入重构，经 Celery worker 消费
  `dialog_stream` 运行。
- **待补齐**：Dialog Agent「消费 `dialog_turn` → 产出 AI 回复 → 发布 `dialog_message`」的
  常驻消费 worker 尚未接入（当前仅有 `dialog_agent_preheat` 预热）。在该 worker 接入前，
  第 3.2 节发送消息后 **SSE 上不会出现 AI 回复**（关键词命中的 `constraint` 事件可正常收到）。
  详见《对接就绪度评估》。
