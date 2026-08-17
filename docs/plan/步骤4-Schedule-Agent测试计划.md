# 步骤4 - Schedule Agent 测试计划

## 测试目标

验证 Schedule Agent 的核心功能：量表问题加载、对话偏离检测、工具调用完整性检查、约束事件发布、任务恢复能力。

---

## 测试环境

- **Python 版本**: 3.11
- **测试框架**: pytest
- **Mock 框架**: pytest-mock
- **异步测试**: pytest-asyncio
- **数据库**: PostgreSQL (测试库使用外层事务回滚)
- **Redis**: 本地 Redis 实例
- **LLM Mock**: 使用 Mock 对象模拟 AsyncOpenAI 响应

---

## 测试文件结构

```
backend/tests/
├── unit-test/
│   ├── test_assessment_loader.py          # 量表加载器单元测试
│   ├── test_schedule_agent_core.py        # Schedule Agent 核心逻辑测试
│   └── test_schedule_agent_prompts.py     # 提示词模板测试
├── integ-test/
│   ├── test_schedule_agent_celery.py      # Celery 任务集成测试
│   └── test_schedule_agent_redis.py       # Redis Stream 集成测试
└── e2e-test/
    └── test_schedule_agent_workflow.py    # 端到端工作流测试
```

---

## 单元测试计划

### 1. AssessmentQuestionLoader 测试 (`test_assessment_loader.py`)

#### 测试用例列表

| 测试用例 | 描述 | 验收标准 |
|---------|------|---------|
| `test_load_questions_by_scale_codes_success` | 成功加载量表问题 | 返回 QuestionTask 列表，包含所有必答题和选答题 |
| `test_load_questions_filter_derived_fields` | 过滤派生字段（如 BMI） | BMI 等计算字段不出现在结果中 |
| `test_load_questions_multiple_scales` | 加载多个量表 | 按量表顺序返回所有问题 |
| `test_load_questions_empty_scale_codes` | 空量表编码列表 | 返回空列表 |
| `test_load_questions_invalid_scale_code` | 无效量表编码 | 记录警告日志，返回空列表或跳过无效编码 |
| `test_load_questions_database_error` | 数据库查询失败 | 抛出异常或返回空列表 |

#### 关键断言

```python
# 示例：验证加载结果结构
def test_load_questions_by_scale_codes_success():
    loader = AssessmentQuestionLoader()
    questions = await loader.load_questions_by_scale_codes(["BARTHEL", "NORTON"])
    
    assert len(questions) > 0
    assert all(isinstance(q, QuestionTask) for q in questions)
    assert all(q.question_code for q in questions)
    assert all(q.patient_text for q in questions)
    # 验证派生字段已过滤
    assert not any("BMI" in q.question_code for q in questions)
```

---

### 2. ScheduleAgent 核心逻辑测试 (`test_schedule_agent_core.py`)

#### 测试用例列表

| 测试用例 | 描述 | 验收标准 |
|---------|------|---------|
| `test_agent_initialization` | 智能体初始化 | 成功创建实例，task_list 和 llm_client 赋值正确 |
| `test_evaluate_skip_before_interval` | 未达到检查间隔 | 轮次 < check_interval 时，返回 is_deviation=False |
| `test_evaluate_trigger_at_interval` | 达到检查间隔触发检查 | 轮次 = check_interval 时，调用 LLM 进行偏离检测 |
| `test_deviation_detection_true` | 检测到偏离 | LLM 返回 is_deviation=true，输出约束提示 |
| `test_deviation_detection_false` | 未检测到偏离 | LLM 返回 is_deviation=false，无约束提示 |
| `test_tool_call_check_missing_tool` | 工具调用缺失检测 | 对话提到"吸烟"但未调用宣教工具，标记为偏离 |
| `test_tool_call_check_complete` | 工具调用完整 | 对话提到"吸烟"且调用了宣教工具，不标记偏离 |
| `test_remaining_questions_update` | 剩余问题列表更新 | 识别已回答问题，更新 remaining_questions |
| `test_all_questions_completed` | 所有问题完成 | remaining_questions 为空，返回完成状态 |
| `test_llm_error_handling` | LLM 调用失败 | 超时或错误时返回默认安全结果（不偏离） |
| `test_json_parse_error` | JSON 解析失败 | LLM 返回非 JSON 时记录错误，返回默认结果 |

#### 关键 Mock 示例

```python
# Mock AsyncOpenAI 响应
@pytest.mark.asyncio
async def test_deviation_detection_true(mocker):
    mock_llm = mocker.MagicMock()
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "is_deviation": True,
        "reason": "AI回答了与量表无关的生活服务问题",
        "current_focus": "生活服务咨询",
        "suggested_action": "提醒AI回到量表问题"
    })
    mock_llm.chat.completions.create.return_value = mock_response
    
    agent = ScheduleAgent(
        session_id="test-session",
        task_list=[...],
        llm_client=mock_llm,
        check_interval=1  # 立即触发检查
    )
    
    result = await agent.evaluate([
        {"role": "assistant", "content": "您是否吸烟？"},
        {"role": "user", "content": "食堂在哪里？"},
        {"role": "assistant", "content": "食堂在住院楼一楼"}
    ])
    
    assert result.is_deviation is True
    assert "回到量表问题" in result.constraint_prompt
```

---

### 3. 提示词模板测试 (`test_schedule_agent_prompts.py`)

#### 测试用例列表

| 测试用例 | 描述 | 验收标准 |
|---------|------|---------|
| `test_build_deviation_check_prompt` | 生成用户提示词 | 包含待完成任务、对话历史、轮次信息 |
| `test_format_remaining_tasks` | 格式化任务列表 | 必答题标记【必答】，可选题标记【可选】 |
| `test_format_remaining_tasks_limit` | 任务列表截断 | 超过5个任务时显示"还有 N 个问题待完成" |
| `test_format_dialog_history` | 格式化对话历史 | 角色标签正确（AI/患者/系统） |
| `test_format_dialog_history_empty` | 空对话历史 | 返回"（暂无对话）" |
| `test_few_shot_examples_text` | Few-shot 示例文本 | 包含4个场景示例，格式正确 |

#### 关键断言

```python
def test_build_deviation_check_prompt():
    tasks = [
        QuestionTask(question_code="SMOKE", patient_text="您是否吸烟？", required=True),
        QuestionTask(question_code="DRINK", patient_text="您是否饮酒？", required=False),
    ]
    history = [
        {"role": "assistant", "content": "您是否吸烟？"},
        {"role": "user", "content": "我抽烟"}
    ]
    
    prompt = build_deviation_check_prompt(tasks, history, turn_number=3)
    
    assert "【必答】 您是否吸烟？" in prompt
    assert "【可选】 您是否饮酒？" in prompt
    assert "AI: 您是否吸烟？" in prompt
    assert "患者: 我抽烟" in prompt
    assert "第 3 轮" in prompt
```

---

## 集成测试计划

### 4. Celery 任务集成测试 (`test_schedule_agent_celery.py`)

#### 测试用例列表

| 测试用例 | 描述 | 验收标准 |
|---------|------|---------|
| `test_schedule_agent_worker_start` | 任务启动 | 任务成功启动，订阅 dialog_stream |
| `test_schedule_agent_worker_process_event` | 处理对话事件 | 收到 dialog_turn 事件时调用 agent.evaluate() |
| `test_schedule_agent_worker_publish_constraint` | 发布约束事件 | 检测到偏离时发布 ConstraintEvent |
| `test_schedule_agent_worker_publish_session_end` | 发布会话结束事件 | 所有问题完成时发布 SessionEndEvent |
| `test_schedule_agent_worker_timeout` | 超时退出 | 60秒无消息时任务自动退出 |
| `test_schedule_agent_worker_turn_counter_save` | 轮次计数器保存 | 每次检查后保存到 Redis |
| `test_schedule_agent_worker_turn_counter_restore` | 轮次计数器恢复 | 任务重启时从 Redis 恢复 |
| `test_schedule_agent_worker_llm_config_missing` | LLM 配置缺失 | 返回失败状态，记录错误日志 |
| `test_schedule_agent_worker_scale_codes_missing` | 量表编码缺失 | 返回失败状态，记录错误日志 |
| `test_schedule_agent_worker_retry` | 任务重试 | 异常时触发 Celery 重试机制 |

#### 测试策略

```python
# 使用 Celery eager 模式进行测试
@pytest.fixture
def celery_config():
    return {
        'task_always_eager': True,  # 同步执行任务
        'task_eager_propagates': True,  # 传播异常
    }

@pytest.mark.asyncio
async def test_schedule_agent_worker_publish_constraint(celery_app, redis_client):
    session_id = "test-session-123"
    task_config = {
        "scale_codes": ["BARTHEL"],
        "check_interval": 1
    }
    
    # 预先发布对话事件到 Redis Stream
    redis_client.xadd(
        f"dialog_stream:{session_id}",
        {
            "event_type": "dialog_turn",
            "turn_number": "1",
            "message": "食堂在哪里？"
        }
    )
    
    # 执行任务
    result = schedule_agent_worker.delay(session_id, task_config)
    
    # 验证约束事件发布
    messages = redis_client.xread({f"dialog_stream:{session_id}": "0"})
    constraint_events = [
        msg for msg in messages 
        if msg.get("event_type") == "constraint"
    ]
    
    assert len(constraint_events) > 0
    assert "偏离" in constraint_events[0].get("constraint_prompt", "")
```

---

### 5. Redis Stream 集成测试 (`test_schedule_agent_redis.py`)

#### 测试用例列表

| 测试用例 | 描述 | 验收标准 |
|---------|------|---------|
| `test_subscribe_dialog_stream` | 订阅对话流 | 成功读取 Redis Stream 消息 |
| `test_filter_dialog_turn_events` | 过滤事件类型 | 只处理 dialog_turn 事件 |
| `test_read_multiple_events` | 读取多个事件 | 批量读取并逐个处理 |
| `test_redis_connection_error` | Redis 连接失败 | 记录错误日志，任务退出 |
| `test_message_blocking_timeout` | 阻塞超时 | block=5000 超时后继续下次读取 |
| `test_last_id_tracking` | 消息 ID 追踪 | 每次读取后更新 last_id |

---

## 端到端测试计划

### 6. 完整工作流测试 (`test_schedule_agent_workflow.py`)

#### 测试场景

##### 场景1：正常评估流程

```
1. 创建会话，启动 Schedule Agent 任务
2. Dialog Agent 发布前4轮对话事件（未触发检查）
3. Dialog Agent 发布第5轮对话事件（触发检查）
4. Schedule Agent 判断未偏离，继续
5. Dialog Agent 完成所有问题
6. Schedule Agent 发布 SessionEndEvent
7. 验证：
   - 无 ConstraintEvent 发布
   - SessionEndEvent 包含正确的 total_turns
```

##### 场景2：偏离检测与约束注入

```
1. 创建会话，启动 Schedule Agent 任务
2. Dialog Agent 发布3轮正常对话
3. Dialog Agent 发布2轮偏离对话（询问食堂位置）
4. 第5轮触发检查，Schedule Agent 检测到偏离
5. 发布 ConstraintEvent
6. Dialog Agent 收到约束，回到量表问题
7. 验证：
   - ConstraintEvent 包含正确的约束提示
   - remaining_tasks 正确更新
```

##### 场景3：任务中断与恢复

```
1. 创建会话，启动 Schedule Agent 任务
2. 处理10轮对话（turn_counter=10）
3. 模拟任务中断（杀死 Celery Worker）
4. 验证 Redis 中保存了 turn_counter=10
5. 重启任务
6. 验证从 Redis 恢复 turn_counter
7. 继续处理，不重复检查已完成的轮次
```

##### 场景4：工具调用检查

```
1. 创建会话，启动 Schedule Agent 任务
2. Dialog Agent 询问："您是否吸烟？"
3. 患者回答："我抽烟"
4. Dialog Agent 回复但未调用宣教工具
5. 第5轮触发检查，Schedule Agent 检测到工具调用缺失
6. 发布 ConstraintEvent，提示调用宣教工具
7. 验证：
   - ConstraintEvent 包含工具调用提示
```

---

## 性能测试计划

### 7. 性能指标

| 指标 | 目标值 | 测试方法 |
|-----|--------|---------|
| 单次偏离检测延迟 | < 2秒 | Mock LLM，测量 agent.evaluate() 执行时间 |
| 问题加载延迟 | < 500ms | 测量 load_questions_by_scale_codes() 执行时间 |
| Redis Stream 读取延迟 | < 50ms | 测量 xread 调用时间 |
| 并发会话支持 | > 100 | 启动100个 Schedule Agent 任务，验证无阻塞 |
| 内存占用 | < 50MB/会话 | 监控任务内存使用 |

### 测试脚本

```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_evaluate_latency():
    agent = ScheduleAgent(...)
    
    start = time.time()
    result = await agent.evaluate(dialog_history)
    latency = time.time() - start
    
    assert latency < 2.0, f"Latency too high: {latency}s"
```

---

## 错误场景测试

### 8. 异常处理测试

| 场景 | 预期行为 |
|------|---------|
| LLM 推理超时 | 记录错误，返回默认安全结果（不偏离） |
| LLM 返回非 JSON | 记录错误，返回默认安全结果 |
| Redis 连接断开 | 记录错误，任务退出，Celery 重试 |
| 数据库查询失败 | 记录错误，返回失败状态 |
| 量表编码不存在 | 记录警告，跳过无效编码 |
| dialog_stream 不存在 | 记录错误，任务退出 |

---

## 测试数据准备

### 测试量表数据

```python
# fixtures/assessment_scales.py
TEST_SCALES = [
    {
        "scale_code": "BARTHEL",
        "questions": [
            {"code": "BARTHEL_EAT", "text": "进食", "required": True},
            {"code": "BARTHEL_TRANSFER", "text": "转移", "required": True},
            # ...
        ]
    },
    {
        "scale_code": "NORTON",
        "questions": [
            {"code": "NORTON_PHYSICAL", "text": "身体状况", "required": True},
            {"code": "NORTON_MENTAL", "text": "精神状态", "required": True},
            # ...
        ]
    }
]
```

### Mock 对话历史

```python
# fixtures/dialog_history.py
NORMAL_DIALOG = [
    {"role": "assistant", "content": "您好，我是评估助手，现在开始入院评估"},
    {"role": "user", "content": "好的"},
    {"role": "assistant", "content": "您是否吸烟？"},
    {"role": "user", "content": "我抽烟"},
    {"role": "assistant", "content": "请问您每天大概抽多少支烟？"},
]

DEVIATION_DIALOG = [
    {"role": "assistant", "content": "您是否吸烟？"},
    {"role": "user", "content": "食堂在哪里？"},
    {"role": "assistant", "content": "食堂在住院楼一楼"},
    {"role": "user", "content": "谢谢"},
]
```

---

## 测试执行计划

### 执行顺序

1. **单元测试** (预计 2 小时)
   - `test_assessment_loader.py`
   - `test_schedule_agent_core.py`
   - `test_schedule_agent_prompts.py`

2. **集成测试** (预计 3 小时)
   - `test_schedule_agent_celery.py`
   - `test_schedule_agent_redis.py`

3. **端到端测试** (预计 2 小时)
   - `test_schedule_agent_workflow.py`

4. **性能测试** (预计 1 小时)
   - 延迟测试
   - 并发测试

5. **错误场景测试** (预计 1 小时)

### 测试命令

```bash
# 运行所有 Schedule Agent 测试
pytest backend/tests/ -k "schedule_agent" -v

# 只运行单元测试
pytest backend/tests/unit-test/test_schedule_agent_*.py -v

# 只运行集成测试
pytest backend/tests/integ-test/test_schedule_agent_*.py -v

# 运行性能测试
pytest backend/tests/ -m performance -v

# 生成覆盖率报告
pytest backend/tests/ -k "schedule_agent" --cov=backend/app/managers --cov=backend/packages/medagent/agents/service_agent/schedule_agent --cov-report=html
```

---

## 验收标准

- [ ] 所有单元测试通过（目标 15+ 个用例）
- [ ] 所有集成测试通过（目标 10+ 个用例）
- [ ] 所有端到端测试通过（目标 4+ 个场景）
- [ ] 代码覆盖率 > 80%
- [ ] 性能指标达标
- [ ] 所有异常场景正确处理

---

## 测试报告模板

测试完成后，生成测试报告：`docs/review/步骤4-Schedule-Agent测试报告.md`

内容包括：
- 测试概要（执行时间、通过率）
- 详细测试结果（每个测试文件的通过情况）
- 覆盖率报告（代码覆盖率统计）
- 性能测试结果（延迟、并发、内存）
- 发现的问题（BUG 列表）
- 修复记录
- 结论与建议

---

**创建时间**: 2026-08-17  
**负责人**: AI开发助手  
**状态**: 待执行（等待用户指令）
