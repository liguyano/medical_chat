# API 接口文档 - 第一期文本闭环

**版本**: v1.0  
**日期**: 2026-08-17  
**范围**: 医护端选患者→发任务→AI对话→字段抽取→实时监控的完整后端接口

---

## 1. 总体说明

### 1.1 基础信息

- **Base URL**: `http://localhost:8000`（开发环境）
- **响应格式**: JSON（所有端点返回**裸载荷**，无 `{code, message, data}` 包装）
- **字符编码**: UTF-8
- **时间格式**: ISO 8601（带时区偏移，如 `2026-08-17T10:30:00+08:00`）

### 1.2 通用错误响应

当请求失败时，返回 HTTP 4xx/5xx 状态码，响应体为：

```json
{
  "error_code": "ERR_XXXX_001",
  "message": "错误描述",
  "detail": {} // 可选，额外错误信息
}
```

常见错误码：
- `ERR_COMMON_001`: 参数缺失或格式错误
- `ERR_DIALOG_001`: 会话不存在
- `ERR_DIALOG_002`: 会话已结束
- `ERR_DIALOG_003`: 会话锁定中（并发冲突）
- `ERR_DIALOG_004`: 任务不存在或不支持 AI 对话

---

## 2. 核心接口

### 2.1 获取在院患者列表

**端点**: `GET /api/patients/in-hospital`

**作用**: 医护端选患者时调用，返回当前在院患者及其住院遭遇信息。

**请求参数**: 无

**响应示例**:

```json
[
  {
    "patient": {
      "id": 1,
      "patient_no": "P000001",
      "name": "张三",
      "gender": "男",
      "age": 45,
      "id_number": "110101197901011234",
      "phone": "13800138000",
      "admission_date": "2026-08-15T09:00:00+08:00"
    },
    "encounter": {
      "id": 1,
      "encounter_no": "E20260815001",
      "encounter_type": "inpatient",
      "admission_time": "2026-08-15T09:00:00+08:00",
      "department_code": "CARDIOLOGY",
      "department_name": "心内科",
      "bed_number": "301-01",
      "encounter_status": "admitted"
    }
  }
]
```

**字段说明**:
- `patient.id`: 患者主键（数据库 ID，字符串化）
- `patient.patient_no`: 患者唯一编号（HIS 系统）
- `encounter.encounter_no`: 本次住院遭遇编号
- `encounter.encounter_status`: 遭遇状态（`admitted` 在院 / `discharged` 出院）

---

### 2.2 获取量表列表

**端点**: `GET /api/scales`

**作用**: 医护端选择评估量表时调用，返回已发布的量表及其题目数量。

**请求参数**: 无

**响应示例**:

```json
[
  {
    "scale_code": "ADMISSION_ASSESSMENT",
    "scale_name": "入院评估量表",
    "scale_type": "综合评估",
    "question_count": 12,
    "estimated_duration": 15,
    "description": "患者入院时的基础信息与健康状况评估"
  },
  {
    "scale_code": "PAIN_ASSESSMENT",
    "scale_name": "疼痛评估量表",
    "scale_type": "专项评估",
    "question_count": 8,
    "estimated_duration": 5,
    "description": "评估患者疼痛程度与性质"
  }
]
```

**字段说明**:
- `scale_code`: 量表唯一编码（创建任务时使用）
- `question_count`: 非衍生题目数量（实际问诊题数）
- `estimated_duration`: 预计完成时长（分钟）

---

### 2.3 创建护理任务

**端点**: `POST /api/tasks`

**作用**: 医护端发起任务（评估/宣教/知情同意），AI 对话模式会预创建会话并返回 `session_id`。

**请求体**:

```json
{
  "patient_id": 1,
  "encounter_id": 1,
  "task_type": "assessment",
  "collection_mode": "ai_dialogue",
  "scale_ids": [1, 2],
  "nurse_id": 10,
  "participant_type": "patient",
  "participant_name": "张三",
  "relationship_to_patient": null,
  "assessment_scene": "入院评估",
  "consent_required": false,
  "education_topics": [],
  "planned_start_time": "2026-08-17T14:00:00+08:00",
  "notes": "首次入院，需详细评估"
}
```

**字段说明**:
- `collection_mode`: 必选，枚举：
  - `ai_dialogue`: AI 主导对话（文本/语音）
  - `questionnaire`: 传统问卷（患者自填）
  - `nurse_input`: 护士录入
- `scale_ids`: 量表主键列表（从 `GET /api/scales` 获取）
- `participant_type`: 参与人类型（`patient` 患者 / `family` 家属）
- `assessment_scene`: 评估场景（如 "入院评估" / "日常查房"）

**响应示例**:

```json
{
  "task_id": 1,
  "task_no": "TASK-20260817-001",
  "session_id": "S-TASK-20260817-001",
  "status": "pending",
  "task": {
    "task_id": 1,
    "task_no": "TASK-20260817-001",
    "patient_id": 1,
    "patient_no": "P000001",
    "patient_name": "张三",
    "task_type": "assessment",
    "collection_mode": "ai_dialogue",
    "task_status": "pending",
    "created_at": "2026-08-17T13:45:00+08:00",
    "scales": [
      {
        "scale_id": 1,
        "scale_code": "ADMISSION_ASSESSMENT",
        "scale_name": "入院评估量表"
      }
    ]
  }
}
```

**字段说明**:
- `session_id`: AI 对话模式下预创建的会话 ID（立即可用于 SSE 订阅和发消息）
- `status`: 任务状态（`pending` 待开始 / `in_progress` 进行中 / `completed` 已完成）

---

### 2.4 发送患者消息

**端点**: `POST /api/dialog/message`

**作用**: 患者端发送文本/语音转录后的消息，后端落库并发布事件，AI 回复通过 SSE 异步推送。

**请求体**:

```json
{
  "session_id": "S-TASK-20260817-001",
  "task_id": 1,
  "content": "我今年 45 岁，有高血压病史",
  "client_message_id": "msg-uuid-1234",
  "input_mode": "text"
}
```

**字段说明**:
- `session_id`: 会话 ID（从创建任务响应或 SSE 事件获取）
- `task_id`: 关联任务 ID
- `content`: 消息内容（文本或语音转录文本）
- `client_message_id`: 客户端生成的消息唯一 ID（幂等性标识）
- `input_mode`: 输入模式（`text` 文本 / `voice` 语音）

**响应**: 

```
HTTP/1.1 204 No Content
```

AI 回复不在响应中返回，而是通过 SSE `GET /api/dialog/stream/{session_id}` 推送。

---

### 2.5 获取对话历史

**端点**: `GET /api/dialog/{session_id}/history`

**作用**: 查询会话的历史消息（患者答案 + AI 提问），支持分页。

**请求参数**:
- `limit` (可选): 返回消息数量上限（默认 100）
- `offset` (可选): 偏移量（默认 0）

**响应示例**:

```json
{
  "session_id": "S-TASK-20260817-001",
  "task_id": 1,
  "session_status": "active",
  "answered_question_count": 5,
  "total_question_count": 12,
  "ai_summary": "患者45岁男性，有高血压病史...",
  "messages": [
    {
      "message_id": 1,
      "message_no": "MSG-1234567890abcdef",
      "turn_no": 1,
      "role": "assistant",
      "content": "您好，请问您的年龄和既往病史？",
      "occurred_at": "2026-08-17T14:00:00+08:00"
    },
    {
      "message_id": 2,
      "message_no": "MSG-2345678901bcdefg",
      "turn_no": 1,
      "role": "patient",
      "content": "我今年45岁，有高血压病史",
      "occurred_at": "2026-08-17T14:00:15+08:00"
    }
  ]
}
```

**字段说明**:
- `role`: 消息角色（`assistant` AI 医护 / `patient` 患者）
- `turn_no`: 对话轮次（AI 提问和患者答案共享同一轮次）
- `ai_summary`: AI 生成的对话摘要（用于监控端快速了解进度）

---

### 2.6 获取字段抽取结果

**端点**: `GET /api/extraction/{session_id}/fields`

**作用**: 实时查询 AI 从对话中抽取的结构化字段（供监控端展示）。

**请求参数**: 无

**响应示例**:

```json
{
  "session_id": "S-TASK-20260817-001",
  "fields": [
    {
      "question_id": 101,
      "question_code": "Q_AGE",
      "question_text": "年龄",
      "answer_value": "45",
      "answer_text": "45岁",
      "extraction_confidence": 0.95,
      "extracted_at": "2026-08-17T14:00:20+08:00"
    },
    {
      "question_id": 102,
      "question_code": "Q_MEDICAL_HISTORY",
      "question_text": "既往病史",
      "answer_value": "高血压",
      "answer_text": "高血压病史",
      "extraction_confidence": 0.88,
      "extracted_at": "2026-08-17T14:00:20+08:00"
    }
  ]
}
```

**字段说明**:
- `answer_value`: 结构化答案值（枚举题为选项 code，数值题为数字字符串）
- `answer_text`: 答案显示文本
- `extraction_confidence`: 抽取置信度（0-1，低于阈值需人工复核）

---

## 3. SSE 实时事件流

### 3.1 订阅会话事件流

**端点**: `GET /api/dialog/stream/{session_id}`

**协议**: Server-Sent Events (SSE)

**作用**: 患者端和监控端订阅会话实时事件（AI 提问、字段抽取、进度更新）。

**请求头**:
```
Accept: text/event-stream
Last-Event-ID: 1234567890-0  # 可选，断线续传起点
```

**事件格式**:

所有事件遵循统一的 **SseEnvelope** 格式：

```
event: assistant_text_delta
id: 1723879200000-0
data: {"event_id":"1723879200000-0","event_type":"assistant_text_delta","task_id":"1","session_id":"S-TASK-20260817-001","message_id":"MSG-abc123","occurred_at":"2026-08-17T14:00:00+08:00","payload":{...}}
```

**Envelope 字段**:
- `event_id`: 事件唯一 ID（对应 Redis Stream 消息 ID）
- `event_type`: 前端事件类型（见下表）
- `task_id`: 关联任务 ID
- `session_id`: 会话 ID
- `message_id`: 消息 ID（可选，对话消息事件专用）
- `occurred_at`: 事件发生时间
- `payload`: 事件载荷（根据 `event_type` 不同而变化）

### 3.2 事件类型映射表

| 前端事件类型 (`event_type`) | 后端事件源 | 说明 |
|---|---|---|
| `assistant_text_delta` | `DIALOG_MESSAGE` | AI 提问/回复（文本） |
| `user_transcript_completed` | `PATIENT_ANSWER` | 患者答案已落库 |
| `extraction_updated` | `EXTRACTION_RESULT` | 字段抽取结果更新 |
| `progress_updated` | `TOOL_CALL` / `CONSTRAINT` | 工具调用/约束触发 |
| `task_status_updated` | `SESSION_END` | 会话结束/任务完成 |
| `heartbeat` | 心跳保活 | 空闲 30 秒发送，客户端忽略 |

### 3.3 核心事件载荷示例

#### 3.3.1 AI 提问事件 (`assistant_text_delta`)

```json
{
  "event_type": "assistant_text_delta",
  "payload": {
    "content_text": "您好，请问您的年龄和既往病史？",
    "delta": "您好，请问您的年龄和既往病史？",
    "text": "您好，请问您的年龄和既往病史？",
    "turn_no": 1,
    "question_id": 101,
    "role": "assistant",
    "cicare_stage": "connect"
  }
}
```

**字段说明**:
- `content_text` / `delta` / `text`: 消息内容（三者相同，兼容不同前端消费逻辑）
- `turn_no`: 对话轮次（从 1 开始递增）
- `question_id`: 关联题目 ID（Task-todo 中的题目，可选）
- `cicare_stage`: CICARE 阶段（可选，默认 `connect`）

#### 3.3.2 患者答案事件 (`user_transcript_completed`)

```json
{
  "event_type": "user_transcript_completed",
  "payload": {
    "content_text": "我今年45岁，有高血压病史",
    "text": "我今年45岁，有高血压病史",
    "turn_no": 1,
    "role": "user",
    "client_message_id": "msg-uuid-1234"
  }
}
```

**用途**: 语音模式下前端发送语音片段后，后端转录完成并落库后推送此事件确认。

#### 3.3.3 字段抽取更新 (`extraction_updated`)

```json
{
  "event_type": "extraction_updated",
  "payload": {
    "fields": {
      "101": "45",
      "102": "高血压"
    },
    "confidence_scores": {
      "101": 0.95,
      "102": 0.88
    }
  }
}
```

**字段说明**:
- `fields`: 字段字典（`question_id` → `answer_value`）
- `confidence_scores`: 置信度字典（`question_id` → `confidence`）

**前端处理**: 收到此事件后，应调用 `GET /api/extraction/{session_id}/fields` 获取完整字段列表并更新 UI。

#### 3.3.4 任务状态更新 (`task_status_updated`)

```json
{
  "event_type": "task_status_updated",
  "payload": {
    "status": "completed",
    "end_reason": "completed",
    "total_turns": 12
  }
}
```

**字段说明**:
- `status`: 任务状态（`completed` / `timeout` / `interrupted`）
- `end_reason`: 结束原因
- `total_turns`: 总对话轮次

**前端处理**: 收到 `status: "completed"` 后，应停止等待新消息，展示完成状态。

### 3.4 断线重连

客户端断线后，重连时携带 `Last-Event-ID` 请求头（值为上次收到的 `event_id`），后端从该 ID 之后继续推送未消费的事件：

```
GET /api/dialog/stream/{session_id}
Last-Event-ID: 1723879200000-5
```

---

## 4. 典型交互流程

### 4.1 完整评估流程（AI 对话模式）

```
1. 医护端：GET /api/patients/in-hospital
   → 选择患者

2. 医护端：GET /api/scales
   → 选择量表

3. 医护端：POST /api/tasks
   {
     "patient_id": 1,
     "collection_mode": "ai_dialogue",
     "scale_ids": [1, 2]
   }
   → 响应: {"task_id": 1, "session_id": "S-xxx"}

4. 患者端：GET /api/dialog/stream/S-xxx
   → 建立 SSE 连接，收到开场白事件:
   event: assistant_text_delta
   data: {"payload": {"content_text": "您好，请问您的年龄..."}}

5. 患者端：POST /api/dialog/message
   {
     "session_id": "S-xxx",
     "content": "我今年45岁",
     "input_mode": "text"
   }
   → 204 No Content

6. 患者端：SSE 收到 AI 下一问:
   event: assistant_text_delta
   data: {"payload": {"content_text": "请问您有无既往病史..."}}

7. 监控端：GET /api/dialog/stream/S-xxx
   → 建立 SSE 连接，实时监控对话

8. 监控端：GET /api/extraction/S-xxx/fields
   → 查询已抽取字段

9. 患者端：SSE 收到完成事件:
   event: task_status_updated
   data: {"payload": {"status": "completed"}}

10. 医护端：GET /api/dialog/S-xxx/history
    → 查看完整对话记录并人工复核
```

---

## 5. 注意事项

### 5.1 响应格式

- 所有接口返回**裸载荷**（直接返回数据对象或数组），无 `{code, message, data}` 包装。
- 错误时返回 HTTP 4xx/5xx 状态码 + 错误对象 `{error_code, message, detail}`。

### 5.2 并发控制

- 同一会话的消息发送操作会加锁（`dialog_lock:{session_id}`），并发请求返回 `ERR_DIALOG_003`。
- 建议前端在收到上一条消息的 AI 回复后再允许用户发送下一条。

### 5.3 超时机制

- Dialog Agent 在 5 分钟（60 次 * 5 秒）无患者答案后自动退出，会话状态保持 `active`，可通过监控端人工介入。
- SSE 连接空闲 30 秒发送心跳 `event: ping`，客户端应忽略该事件但保持连接。

### 5.4 数据一致性

- 字段抽取结果（`extraction_updated` 事件）仅为增量提示，完整数据需调用 `GET /api/extraction/{session_id}/fields`。
- 对话历史查询默认返回最近 100 条消息，完整历史需分页查询。

---

## 6. 待补充功能（第二期）

以下功能在第一期不实现，接口预留：

- **语音实时通话**: WebSocket 全双工语音流（`/api/dialog/voice/{session_id}`）
- **人工介入**: 护士接管会话并回复（`POST /api/dialog/intervene`）
- **评价与签名**: 患者满意度评价、护士质量评价、电子签名
- **宣教与知情同意**: 内容推送、播报状态、签名确认

---

## 附录

### A. 数据库 ID 规则

- 所有响应中的数据库主键（`id` 字段）均转换为字符串，避免 JavaScript 大整数精度丢失。
- 业务编号（如 `task_no`, `session_no`）保持字符串格式。

### B. 时区处理

- 后端存储使用 UTC 时间，响应时转换为东八区 (`+08:00`)。
- 前端发送时间字段需携带时区偏移（ISO 8601 格式）。

### C. 联调环境配置

前端 `.env.local` 配置示例：

```bash
NEXT_PUBLIC_DATA_MODE=api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_TIMEOUT=30000
```

---

**文档版本**: v1.0  
**最后更新**: 2026-08-17  
**维护者**: Backend Team
