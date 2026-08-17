# 第一期文本问诊 API 接口文档

版本：`1.0.0`

更新日期：`2026-08-17`

范围：在院患者、已发布量表、AI 对话任务、患者文本回答、字段抽取、患者/护士 SSE。

## 1. 通用约定

- Base URL：`http://localhost:8000`
- 编码：UTF-8
- 时间：ISO 8601
- 数据库主键为 JSON number；前端应在 DTO 映射边界转为 string。
- 第一期只支持 `collection_mode=ai_dialogue` 的文本问诊。
- AI 扮演医护人员并先问；患者回答后，AI 产生下一问。

除健康检查与 SSE 外，REST 接口统一返回：

```json
{
  "code": "OK",
  "message": "成功",
  "data": {}
}
```

前端必须同时检查 HTTP 状态码和 `code`。成功恒为 `OK`，失败为 `ERR_*`。

健康检查：

```http
GET /health
```

```json
{"status":"ok"}
```

## 2. 在院患者

```http
GET /api/patients/in-hospital
```

响应 `data`：

```json
[
  {
    "patient": {
      "id": 69,
      "patient_no": "P-DEMO-0004",
      "patient_name": "陈建军",
      "sex": "男",
      "birthday": "1968-01-18",
      "phone": "13800000004"
    },
    "encounter": {
      "id": 69,
      "encounter_no": "E-DEMO-0004",
      "inpatient_no": "ZY0004",
      "patient_id": 69,
      "department_code": "RESP",
      "department_name": "呼吸与危重症医学科",
      "ward_name": "呼吸内科病区",
      "bed_no": "16-1",
      "admission_time": "2026-08-16T21:52:56+08:00",
      "encounter_status": "在院",
      "diagnosis_snapshot": {}
    }
  }
]
```

## 3. 已发布量表

```http
GET /api/scales
```

响应 `data`：

```json
[
  {
    "id": 105,
    "scale_code": "adl",
    "scale_name": "日常生活能力(ADL)评价表",
    "scale_type": "assessment_scale",
    "question_count": 10,
    "version_code": "draft-2026-08-13-52802a3acdf6",
    "description": null
  }
]
```

只返回当前生效、`publish_status=已发布` 的版本；`question_count` 排除衍生题。

## 4. 任务

### 4.1 创建并启动 AI 对话任务

```http
POST /api/tasks
Content-Type: application/json
```

请求：

```json
{
  "patient_id": 70,
  "encounter_id": 70,
  "scale_ids": [105],
  "collection_mode": "ai_dialogue",
  "participant_type": "patient",
  "assessment_scene": "admission",
  "assigned_nurse_id": 1,
  "planned_start_time": null,
  "task_type": "assessment",
  "task_name": "入院量表评估",
  "task_source": "manual"
}
```

枚举：

- `collection_mode`：`traditional_form | ai_dialogue`
- `participant_type`：`patient | family | agent`
- `assessment_scene`：`admission | reassessment | transfer | discharge`

第一期前端只提交 `ai_dialogue`。请求成功后，后端在同一事务创建：

1. `care_task`
2. `interaction_session`
3. 每张量表一个 `assessment_instance`

事务提交后派发：

- `dialog_agent_preheat`
- `dialog_agent_worker`
- `schedule_agent_worker`
- `extraction_agent_worker`

响应 `data`：

```json
{
  "task_id": 65,
  "task_no": "TASK-D634B8C90C99",
  "session_id": "SESS-AC1C3800DB3B",
  "status": "in_progress",
  "task": {
    "id": 65,
    "task_id": 65,
    "task_no": "TASK-D634B8C90C99",
    "session_id": "SESS-AC1C3800DB3B",
    "patient_id": 70,
    "encounter_id": 70,
    "encounter_no": "E-DEMO-0005",
    "patient_name": "赵敏",
    "bed_no": "22-2",
    "department": "骨科",
    "ward_name": "骨科病区",
    "task_type": "assessment",
    "collection_mode": "ai_dialogue",
    "task_status": "in_progress",
    "assigned_nurse_id": 1,
    "scale_ids": [105],
    "scale_names": ["日常生活能力(ADL)评价表"],
    "scale_version": "draft-2026-08-13-52802a3acdf6",
    "participant_type": "patient",
    "assessment_scene": "admission",
    "answered_question_count": 0,
    "total_question_count": 10,
    "created_at": "2026-08-17T23:47:32+08:00"
  }
}
```

AI 首问可能在 REST 响应前后立即产生。SSE 首次连接默认从 Stream 起点回放，不会漏掉首问。

### 4.2 获取任务详情

```http
GET /api/tasks/{task_ref}
```

`task_ref` 可传数据库主键或 `TASK-*` 业务编号。响应 `data` 为上面的 `task` 对象。

## 5. 对话

### 5.1 发送患者答案

```http
POST /api/dialog/message
Content-Type: application/json
```

```json
{
  "session_id": "SESS-AC1C3800DB3B",
  "task_id": 65,
  "content": "我可以自己吃饭，不需要帮助",
  "client_message_id": "7b232272-109f-47f5-a355-0c34f624b97e",
  "input_mode": "text"
}
```

- `client_message_id` 是全局幂等键，重试不得生成新值。
- 患者答案与当前 AI 问句使用相同 `turn_no`。
- 当前问题已回答时返回 `ERR_DIALOG_003`。
- AI 下一问不在 REST 响应中返回，只通过 SSE 推送。

响应 `data`：

```json
{
  "session_no": "SESS-AC1C3800DB3B",
  "message_no": "7b232272-109f-47f5-a355-0c34f624b97e",
  "turn_no": 1,
  "intercepted": false
}
```

### 5.2 对话历史

```http
GET /api/dialog/{session_no}/history?limit=100&offset=0
```

响应 `data`：

```json
{
  "session_id": "SESS-AC1C3800DB3B",
  "task_id": 65,
  "task_no": "TASK-D634B8C90C99",
  "session_status": "active",
  "answered_question_count": 1,
  "total_question_count": 10,
  "ai_summary": null,
  "total": 3,
  "messages": [
    {
      "message_no": "MSG-1",
      "turn_no": 1,
      "role_type": "AI",
      "message_type": "文本",
      "content_text": "请问您的进食情况是怎样的？",
      "occurred_at": "2026-08-17T23:47:59+08:00"
    }
  ]
}
```

## 6. 字段抽取

```http
GET /api/extraction/{session_no}/fields
```

响应 `data`：

```json
{
  "session_id": "SESS-AC1C3800DB3B",
  "fields": [
    {
      "field_id": "1001",
      "question_id": 1461,
      "question_code": "feeding",
      "question_text": "进食",
      "answer_text": null,
      "answer_number": null,
      "answer_boolean": null,
      "selected_options": ["independent"],
      "source_message_ids": ["7b232272-109f-47f5-a355-0c34f624b97e"],
      "confidence": 0.96,
      "corrected": false
    }
  ]
}
```

多量表任务会分别写入各自 `assessment_instance / assessment_submission`。

## 7. SSE

患者端：

```http
GET /api/sse/dialog/{session_no}
```

护士单会话监控：

```http
GET /api/sse/monitor/{session_no}
```

断线续传可使用：

- HTTP `Last-Event-ID` 请求头
- `last_event_id` 查询参数（浏览器自定义重连使用）

SSE 帧：

```text
event: assistant_text_delta
id: 1786980944065-0
data: {"event_id":"1786980944065-0","event_type":"assistant_text_delta","task_id":"65","session_id":"SESS-...","message_id":"MSG-...","occurred_at":"2026-08-17T15:35:44Z","payload":{}}
```

事件：

| event | 用途 | payload 核心字段 |
| --- | --- | --- |
| `assistant_text_delta` | AI 问诊问题（当前为整句） | `content_text`, `delta`, `is_final=true`, `turn_no`, `question_id`, `role` |
| `user_transcript_completed` | 患者答案已落库 | `content_text`, `turn_no`, `client_message_id` |
| `extraction_updated` | 抽取字段增量 | `fields[]`, `confidence_scores` |
| `progress_updated` | 约束或工具调用 | `message`, `detail` |
| `task_status_updated` | 会话完成 | `task_status=pending_review`, `end_reason`, `total_turns` |
| `ping` | 30 秒心跳 | 空 |
| `error` | Stream 读取失败 | `message` |

`dialog_turn` 是 Agent 内部协作事件，不向前端推送。

## 8. 错误码

| code | HTTP | 说明 |
| --- | ---: | --- |
| `ERR_COMMON_001` | 422 | 请求参数校验失败 |
| `ERR_COMMON_002` | 404 | 资源不存在 |
| `ERR_COMMON_003` | 409 | 资源状态冲突 |
| `ERR_COMMON_500` | 500 | 服务器内部错误 |
| `ERR_TASK_001` | 404 | 患者不存在 |
| `ERR_TASK_002` | 404 | 住院记录不存在或不属于患者 |
| `ERR_TASK_003` | 404 | 任务不存在 |
| `ERR_TASK_004` | 422 | 量表不存在、未发布或已失效 |
| `ERR_TASK_005` | 503 | Worker 派发失败 |
| `ERR_DIALOG_001` | 404 | 会话不存在 |
| `ERR_DIALOG_002` | 409 | 会话状态不允许或首问未就绪 |
| `ERR_DIALOG_003` | 409 | 并发冲突或当前问题已回答 |
| `ERR_DIALOG_004` | 404 | 任务与会话不匹配 |
| `ERR_SSE_001` | 404 | 会话事件流不存在 |
| `ERR_KEYWORD_001` | 500 | 关键词规则加载失败 |

## 9. 前端时序

```text
GET  /api/patients/in-hospital
GET  /api/scales
POST /api/tasks
  ├─ 立即保存 task_id/task_no/session_id
  └─ 立即连接两个 SSE 之一
GET  /api/sse/dialog/{session_id}
  └─ 收到 AI 首问
POST /api/dialog/message
  └─ 仅确认患者答案已接收
SSE assistant_text_delta
  └─ 收到 AI 下一问
SSE extraction_updated
  └─ 更新结构化字段
GET  /api/dialog/{session_id}/history
GET  /api/extraction/{session_id}/fields
```

## 10. Worker 启动

这些任务是长驻 Stream 消费者。Windows `solo` 模式不能用一个 Worker 同时消费三个队列，
必须分别启动：

```powershell
uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q dialog_queue -n dialog@%h --loglevel=info
uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q schedule_queue -n schedule@%h --loglevel=info
uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q extraction_queue -n extraction@%h --loglevel=info
```

本机配置使用 `localhost` 时，应用会规范化为 `127.0.0.1`，避免 Windows IPv6 解析超时。

## 11. 第一期不支持

以下原型能力没有真实后端接口，API 模式不得调用：

- 实时语音
- 暂停/恢复
- 人工介入
- 知情同意与签名
- 宣教
- 点赞/点踩与质量评价
- 传统问卷
- 护士复核提交
