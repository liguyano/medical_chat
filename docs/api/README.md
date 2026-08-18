# API接口文档

## 基本信息

- **Base URL**: `http://localhost:8000`
- **API版本**: `v1`
- **认证方式**: JWT Bearer Token
- **内容类型**: `application/json`
- **字符编码**: `UTF-8`

---

## 通用响应格式

### 成功响应
```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

### 错误响应
```json
{
  "code": 400,
  "message": "错误描述",
  "detail": "详细错误信息（可选）"
}
```

### HTTP状态码
- `200` - 请求成功
- `201` - 创建成功
- `400` - 请求参数错误
- `401` - 未授权
- `403` - 禁止访问
- `404` - 资源不存在
- `500` - 服务器内部错误

---

## 1. 评估任务管理

### 1.1 创建评估任务

**接口**: `POST /api/tasks`

**描述**: 医护端为患者创建评估任务，支持传统问卷和AI对话两种方式

**请求头**:
```
Authorization: Bearer {token}
Content-Type: application/json
```

**请求体**:
```json
{
  "patient_id": 1001,
  "nurse_id": 2001,
  "department_id": 301,
  "form_ids": ["pain_scale", "fall_risk", "nutrition_assessment"],
  "task_type": "ai_dialog"
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| patient_id | integer | 是 | 患者ID |
| nurse_id | integer | 是 | 创建任务的护士ID |
| department_id | integer | 是 | 科室ID |
| form_ids | array[string] | 是 | 量表ID列表，至少包含一个 |
| task_type | string | 是 | 任务类型：`questionnaire`(传统问卷) 或 `ai_dialog`(AI对话) |

**成功响应** (201):
```json
{
  "code": 201,
  "message": "任务创建成功",
  "data": {
    "task_id": 100001,
    "task_no": "TASK-20260816-A1B2C3",
    "session_id": "sess_1a2b3c4d5e6f",
    "status": "pending",
    "created_at": "2026-08-16T10:30:00Z"
  }
}
```

**错误响应**:
```json
{
  "code": 400,
  "message": "参数错误",
  "detail": "form_ids不能为空"
}
```

---

### 1.2 获取任务详情

**接口**: `GET /api/tasks/{task_id}`

**描述**: 获取指定评估任务的详细信息

**路径参数**:
- `task_id` (integer) - 任务ID

**成功响应** (200):
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "task_id": 100001,
    "task_no": "TASK-20260816-A1B2C3",
    "patient_id": 1001,
    "patient_name": "张三",
    "nurse_id": 2001,
    "nurse_name": "李护士",
    "department_id": 301,
    "department_name": "心内科",
    "form_ids": ["pain_scale", "fall_risk"],
    "task_type": "ai_dialog",
    "status": "in_progress",
    "created_at": "2026-08-16T10:30:00Z",
    "started_at": "2026-08-16T10:35:00Z",
    "completed_at": null,
    "session_id": "sess_1a2b3c4d5e6f"
  }
}
```

---

### 1.3 取消任务

**接口**: `POST /api/tasks/{task_id}/cancel`

**描述**: 取消正在进行的评估任务

**路径参数**:
- `task_id` (integer) - 任务ID

**请求体**:
```json
{
  "reason": "患者不配合"
}
```

**成功响应** (200):
```json
{
  "code": 200,
  "message": "任务已取消",
  "data": {
    "task_id": 100001,
    "status": "cancelled"
  }
}
```

---

### 1.4 查询任务列表

**接口**: `GET /api/tasks`

**描述**: 查询评估任务列表，支持分页和筛选

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| patient_id | integer | 否 | 患者ID |
| nurse_id | integer | 否 | 护士ID |
| status | string | 否 | 任务状态：`pending`/`in_progress`/`completed`/`cancelled` |
| task_type | string | 否 | 任务类型：`questionnaire`/`ai_dialog` |
| page | integer | 否 | 页码，默认1 |
| page_size | integer | 否 | 每页数量，默认20，最大100 |

**成功响应** (200):
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "task_id": 100001,
        "task_no": "TASK-20260816-A1B2C3",
        "patient_id": 1001,
        "patient_name": "张三",
        "status": "in_progress",
        "created_at": "2026-08-16T10:30:00Z"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

---

## 2. 对话交互

### 2.1 发送消息

**接口**: `POST /api/dialog/message`

**描述**: 患者端发送消息给AI对话智能体

**请求体**:
```json
{
  "session_id": "sess_1a2b3c4d5e6f",
  "user_input": "我今天有点疼",
  "input_type": "text",
  "audio_data": null
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话ID |
| user_input | string | 是 | 用户输入内容（文本） |
| input_type | string | 是 | 输入类型：`text`(文本) 或 `audio`(语音) |
| audio_data | string | 否 | 语音数据（base64编码），仅当input_type为audio时必填 |

**成功响应** (200):
返回SSE流式响应，Content-Type: `text/event-stream`

```
event: dialog_message
id: msg_1234567890
data: {"type": "text", "content": "您好，请问疼痛在哪个部位？", "timestamp": "2026-08-16T10:35:01Z"}

event: dialog_message
id: msg_1234567891
data: {"type": "text", "content": "疼痛等级从1到10，您觉得是几分？", "timestamp": "2026-08-16T10:35:03Z"}

event: progress_update
id: progress_1234567892
data: {"completed_fields": 3, "total_fields": 15, "percentage": 20.0}
```

---

### 2.2 获取对话历史

**接口**: `GET /api/dialog/{session_id}/history`

**描述**: 获取指定会话的对话历史记录

**路径参数**:
- `session_id` (string) - 会话ID

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 返回条数，默认50，最大200 |
| offset | integer | 否 | 偏移量，默认0 |

**成功响应** (200):
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "messages": [
      {
        "message_id": "msg_1234567890",
        "turn_number": 1,
        "role": "assistant",
        "content": "您好，我是AI护理助手小智，很高兴为您服务。请问我可以叫您什么？",
        "content_type": "text",
        "created_at": "2026-08-16T10:35:00Z"
      },
      {
        "message_id": "msg_1234567891",
        "turn_number": 1,
        "role": "user",
        "content": "叫我张大爷就好",
        "content_type": "text",
        "created_at": "2026-08-16T10:35:15Z"
      },
      {
        "message_id": "msg_1234567892",
        "turn_number": 2,
        "role": "assistant",
        "content": "好的张大爷，请问您今天身体感觉怎么样？",
        "content_type": "text",
        "tool_calls": null,
        "created_at": "2026-08-16T10:35:17Z"
      }
    ],
    "total": 50
  }
}
```

---

### 2.3 暂停对话

**接口**: `POST /api/dialog/{session_id}/pause`

**描述**: 暂停正在进行的对话

**路径参数**:
- `session_id` (string) - 会话ID

**成功响应** (200):
```json
{
  "code": 200,
  "message": "对话已暂停",
  "data": {
    "session_id": "sess_1a2b3c4d5e6f",
    "status": "paused"
  }
}
```

---

### 2.4 恢复对话

**接口**: `POST /api/dialog/{session_id}/resume`

**描述**: 恢复已暂停的对话

**路径参数**:
- `session_id` (string) - 会话ID

**成功响应** (200):
```json
{
  "code": 200,
  "message": "对话已恢复",
  "data": {
    "session_id": "sess_1a2b3c4d5e6f",
    "status": "active"
  }
}
```

---

## 3. SSE流式推送

### 3.1 患者端对话流订阅

**接口**: `GET /api/sse/dialog/{session_id}`

**描述**: 患者端订阅对话流，接收AI实时回复（支持断线重连）

**路径参数**:
- `session_id` (string) - 会话ID

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| last_event_id | string | 否 | 最后接收的事件ID，用于断线重连 |

**响应** (200):
Content-Type: `text/event-stream`

**事件类型**:

#### dialog_message - 对话消息
```
event: dialog_message
id: msg_1234567890
data: {
  "message_id": "msg_1234567890",
  "role": "assistant",
  "content": "您好，请问您是否吸烟？",
  "timestamp": "2026-08-16T10:35:01Z"
}
```

#### progress_update - 进度更新
```
event: progress_update
id: progress_1234567892
data: {
  "completed_fields": 8,
  "total_fields": 20,
  "percentage": 40.0,
  "latest_field": {
    "field_key": "smoking_status",
    "field_value": "是",
    "confidence": 0.95
  }
}
```

#### tool_call - 工具调用
```
event: tool_call
id: tool_1234567893
data: {
  "tool_name": "get_education_material",
  "args": {"category": "tobacco", "level": 2},
  "status": "executing"
}
```

#### education_material - 宣教材料推送
```
event: education_material
id: edu_1234567894
data: {
  "education_type": "tobacco",
  "level": 2,
  "material_id": "tobacco_edu_002",
  "content": "吸烟对健康的危害...",
  "should_play_audio": true
}
```

#### consent_form - 知情同意书推送
```
event: consent_form
id: consent_1234567895
data: {
  "form_id": "consent_tobacco_001",
  "form_type": "tobacco",
  "content": "烟草使用知情同意书...",
  "signature_required": true
}
```

#### error - 错误信息
```
event: error
id: error_1234567896
data: {
  "error_code": "MODEL_TIMEOUT",
  "message": "AI响应超时，正在重试...",
  "recoverable": true
}
```

#### heartbeat - 心跳保活
```
event: heartbeat
id: heartbeat_1234567897
data: {"timestamp": "2026-08-16T10:35:30Z"}
```

---

### 3.2 医护端监控流订阅

**接口**: `GET /api/sse/monitor`

**描述**: 医护端监控所有负责患者的对话情况

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| nurse_id | integer | 是 | 护士ID |

**响应** (200):
Content-Type: `text/event-stream`

```
event: monitor_message
id: monitor_1234567900
data: {
  "session_id": "sess_1a2b3c4d5e6f",
  "patient_id": 1001,
  "patient_name": "张三",
  "message_id": "msg_1234567890",
  "role": "assistant",
  "content": "您好，请问您是否吸烟？",
  "timestamp": "2026-08-16T10:35:01Z"
}

event: monitor_alert
id: alert_1234567901
data: {
  "session_id": "sess_1a2b3c4d5e6f",
  "alert_type": "patient_timeout",
  "message": "患者已超过5分钟无响应",
  "timestamp": "2026-08-16T10:40:01Z"
}
```

---

## 4. 字段抽取结果

### 4.1 获取抽取字段

**接口**: `GET /api/extraction/{session_id}/fields`

**描述**: 获取指定会话的字段抽取结果和进度

**路径参数**:
- `session_id` (string) - 会话ID

**成功响应** (200):
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "fields": [
      {
        "id": 10001,
        "form_id": "pain_scale",
        "field_key": "pain_location",
        "field_label": "疼痛部位",
        "field_value": "胸部",
        "confidence": 0.95,
        "is_confirmed": true,
        "source_message_id": "msg_1234567892",
        "extraction_time": "2026-08-16T10:35:20Z"
      },
      {
        "id": 10002,
        "form_id": "pain_scale",
        "field_key": "pain_level",
        "field_label": "疼痛等级",
        "field_value": "7",
        "confidence": 0.68,
        "is_confirmed": false,
        "source_message_id": "msg_1234567895",
        "extraction_time": "2026-08-16T10:36:10Z"
      }
    ],
    "progress": {
      "total_fields": 20,
      "completed_fields": 12,
      "confirmed_fields": 10,
      "pending_confirmation": 2,
      "percentage": 60.0
    }
  }
}
```

---

### 4.2 人工确认字段

**接口**: `POST /api/extraction/fields/{field_id}/confirm`

**描述**: 护士人工确认或修正抽取字段

**路径参数**:
- `field_id` (integer) - 字段ID

**请求体**:
```json
{
  "confirmed_value": "8",
  "nurse_id": 2001,
  "comment": "患者表情痛苦，疼痛等级应为8分"
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| confirmed_value | string | 是 | 确认后的字段值 |
| nurse_id | integer | 是 | 确认人ID |
| comment | string | 否 | 确认备注 |

**成功响应** (200):
```json
{
  "code": 200,
  "message": "字段已确认",
  "data": {
    "field_id": 10002,
    "field_value": "8",
    "is_confirmed": true,
    "confirmed_by": 2001,
    "confirmed_at": "2026-08-16T10:37:00Z"
  }
}
```

---

## 5. 护士评分

### 5.1 对消息评分

**接口**: `POST /api/rating`

**描述**: 护士对AI回复进行点赞/踩或提出意见

**请求体**:
```json
{
  "task_id": "3",
  "message_id": "msg_1234567890",
  "reviewer_id": 2001,
  "rating": "like",
  "score": 5,
  "issue_tags": [],
  "comment": "回复很自然，符合老年人沟通习惯"
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | 是 | 任务ID或任务编号 |
| message_id | string | 是 | 消息ID或消息编号 |
| reviewer_id | integer | 否 | 护士ID，未接入真实医护鉴权时为0 |
| rating | string | 否 | 评分类型：`like`(点赞) 或 `dislike`(踩) |
| score | integer | 否 | 1～5分；与 `rating` 至少填写一项 |
| issue_tags | array | 否 | 问题标签数组 |
| comment | string | 否 | 评价意见 |

**成功响应** (200):
```json
{
  "code": 200,
  "message": "评分成功",
  "data": {
    "feedback_id": 50001,
    "task_id": "3",
    "message_id": "msg_1234567890",
    "reviewer_id": 2001,
    "rating": "like",
    "score": 5,
    "issue_tags": [],
    "comment": "回复很自然，符合老年人沟通习惯",
    "reviewed_at": "2026-08-16T10:38:00Z"
  }
}
```

### 5.2 查询任务逐条评分

**接口**: `GET /api/rating?task_id={task_id}&reviewer_id={reviewer_id}`

**描述**: 查询指定护士在任务下已经保存的逐条 AI 消息质评。

### 5.3 提交整体AI质量评价

**接口**: `POST /api/quality-reviews`

**描述**: 按对话质量和评估质量两个模板保存1～5分维度评价、维度意见、证据消息和总体意见。

### 5.4 查询整体AI质量评价

**接口**: `GET /api/quality-reviews/{task_id}?reviewer_id={reviewer_id}`

**描述**: 查询指定护士对任务的最新整体质量评价。

---

## 6. 宣教与知情同意书

### 6.1 获取宣教材料

**接口**: `GET /api/education/materials`

**描述**: 获取指定类别和级别的宣教材料

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category | string | 是 | 宣教类别：`tobacco`/`alcohol`/`diabetes`/`allergy`等 |
| level | integer | 否 | 宣教级别：1-3，默认1 |

**成功响应** (200):
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "material_id": "tobacco_edu_002",
    "category": "tobacco",
    "level": 2,
    "title": "吸烟对健康的危害",
    "content": "吸烟是导致多种疾病的重要危险因素...",
    "audio_url": "https://oss.example.com/education/tobacco_002.mp3",
    "duration": 120
  }
}
```

---

### 6.2 获取知情同意书

**接口**: `GET /api/consent-forms/{form_type}`

**描述**: 获取指定类型的知情同意书

**路径参数**:
- `form_type` (string) - 表单类型：`surgery`/`anesthesia`/`blood_transfusion`/`tobacco`等

**成功响应** (200):
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "form_id": "consent_tobacco_001",
    "form_type": "tobacco",
    "title": "烟草使用知情同意书",
    "content": "本人已充分了解吸烟的危害，包括但不限于...",
    "signature_required": true,
    "version": "v1.0"
  }
}
```

---

### 6.3 提交签名

**接口**: `POST /api/consent-forms/{form_id}/sign`

**描述**: 患者提交知情同意书签名

**路径参数**:
- `form_id` (string) - 表单ID

**请求体**:
```json
{
  "session_id": "sess_1a2b3c4d5e6f",
  "signature_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```

**参数说明**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话ID |
| signature_data | string | 是 | 签名图片（base64格式） |

**成功响应** (200):
```json
{
  "code": 200,
  "message": "签名成功",
  "data": {
    "form_id": "consent_tobacco_001",
    "is_signed": true,
    "signature_url": "https://oss.example.com/signatures/consent_tobacco_001_patient1001.png",
    "signed_at": "2026-08-16T10:40:00Z"
  }
}
```

---

## 7. 健康检查

### 7.1 健康检查

**接口**: `GET /api/health`

**描述**: 检查服务健康状态

**成功响应** (200):
```json
{
  "status": "healthy",
  "timestamp": "2026-08-16T10:45:00Z",
  "services": {
    "database": "healthy",
    "redis": "healthy",
    "celery": "healthy"
  }
}
```

---

## 附录

### A. 错误码列表

| 错误码 | 说明 |
|--------|------|
| 1001 | 参数缺失 |
| 1002 | 参数格式错误 |
| 2001 | 任务不存在 |
| 2002 | 会话不存在 |
| 2003 | 会话已过期 |
| 3001 | 模型推理失败 |
| 3002 | 模型推理超时 |
| 4001 | Redis连接失败 |
| 4002 | 数据库连接失败 |
| 5001 | 权限不足 |

### B. 前端EventSource示例

```javascript
// 患者端SSE订阅
let lastEventId = localStorage.getItem('last_event_id') || '';

function connectSSE() {
  const url = `/api/sse/dialog/${sessionId}${lastEventId ? '?last_event_id=' + lastEventId : ''}`;
  const eventSource = new EventSource(url);
  
  eventSource.addEventListener('dialog_message', (event) => {
    lastEventId = event.lastEventId;
    localStorage.setItem('last_event_id', lastEventId);
    
    const data = JSON.parse(event.data);
    displayMessage(data);
  });
  
  eventSource.addEventListener('progress_update', (event) => {
    const data = JSON.parse(event.data);
    updateProgress(data);
  });
  
  eventSource.addEventListener('consent_form', (event) => {
    const data = JSON.parse(event.data);
    showConsentForm(data);
  });
  
  eventSource.onerror = () => {
    eventSource.close();
    setTimeout(connectSSE, 5000); // 5秒后重连
  };
}

connectSSE();
```

---

**文档版本**: v1.0  
**最后更新**: 2026-08-16
