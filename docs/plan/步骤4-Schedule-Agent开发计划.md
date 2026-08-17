# 步骤4：Schedule Agent 开发计划

## 一、目标概述

开发 Schedule Agent（调度智能体），作为 AI 对话评估流程的调度器，负责：
1. 根据量表配置生成结构化问题列表
2. 监控 Dialog Agent 对话进度
3. 检测对话是否偏离量表问题
4. 检查工具调用完整性
5. 发布约束提示到 Redis Stream

## 二、核心决策记录

| 决策项 | 方案 |
|--------|------|
| **偏离检测算法** | 基于 LLM 语义判断（方案A） |
| **代码位置** | `backend/packages/medagent/agents/service_agent/schedule_agent/` |
| **触发频率** | 每5轮对话检查一次（降低频率） |
| **量表数据来源** | 从 `assessment_question` 表读取，按 `sort_no` 排序 |
| **状态持久化** | Redis（TTL=1小时），检查点保存到数据库 |
| **任务封装** | Celery 长驻任务，订阅 `dialog_stream:{session_id}` |

## 三、数据结构理解

### 3.1 量表数据模型（来自 `assessment_template.py`）

```python
# 量表主档
AssessmentScale -> scale_code, scale_name, scale_type

# 量表版本
AssessmentScaleVersion -> version_code, scale_snapshot (JSONB)

# 量表分组
AssessmentSection -> section_code, section_name, sort_no

# 量表问题（核心）
AssessmentQuestion:
    - question_code: 题目编码
    - question_name: 题目名称
    - original_text: 原量表文字
    - patient_text: 口语化问题（AI对话使用）
    - question_type: 单选/多选/文本/数字/日期/布尔
    - required: 是否必答
    - scored: 是否参与计分
    - derived: 是否为计算字段（BMI等）
    - sort_no: 排序

# 量表选项
AssessmentOption:
    - option_label: 选项文案
    - option_value: 程序值
    - clinical_score: 临床分值
    - requires_follow_up: 是否需要追问
```

### 3.2 Schedule Agent 核心数据流

```text
医护端创建任务 -> care_task (包含 form_ids)
    ↓
Schedule Agent 启动:
    1. 读取 form_ids 对应的量表版本
    2. 从 assessment_question 读取所有问题（按 sort_no 排序）
    3. 过滤掉 derived=1 的计算题
    4. 生成 TaskList（待完成问题列表）
    ↓
订阅 dialog_stream:{session_id}
    ↓
每5轮对话检查一次:
    1. 调用 LLM 判断是否偏离
    2. 检查是否遗漏工具调用
    3. 发布 ConstraintEvent（如果需要）
    ↓
所有问题完成 -> 发布 SessionEndEvent
```

## 四、开发步骤详细拆解

### 4.1 数据层：量表问题加载器（1-2小时）

**文件位置**: `backend/app/managers/assessment_loader.py`

**功能**:
- [x] 从数据库加载量表问题列表
- [x] 过滤 `derived=1` 的计算题
- [x] 按 `sort_no` 排序
- [x] 返回结构化问题列表

**实现代码框架**:
```python
class AssessmentQuestionLoader:
    """量表问题加载器"""
    
    async def load_questions_by_form_ids(
        self, 
        form_ids: List[str]
    ) -> List[QuestionTask]:
        """
        根据量表ID列表加载所有问题
        Args:
            - form_ids: 量表ID列表 (例如 ["ADL", "NRS2002"])
        Return:
            - questions: QuestionTask列表
        """
        pass
    
    async def get_scale_version(self, scale_code: str) -> int:
        """获取量表当前生效版本"""
        pass
```

**验收标准**:
- [x] 能正确加载多个量表的问题
- [x] 自动过滤计算题
- [x] 返回的问题按顺序排列

---

### 4.2 核心逻辑：Schedule Agent 实现（3-4小时）

**文件位置**: `backend/packages/medagent/agents/service_agent/schedule_agent/agent.py`

**功能**:
- [x] 生成任务列表（TaskList）
- [x] 基于 LLM 的偏离检测
- [x] 工具调用完整性检查
- [x] 输出结构化 `ScheduleAgentOutput`

**实现代码框架**:
```python
from pydantic import BaseModel
from typing import List, Dict, Any

class QuestionTask(BaseModel):
    """单个量表问题任务"""
    question_id: int
    question_code: str
    patient_text: str  # 口语化问题
    question_type: str
    required: bool
    completed: bool = False

class ScheduleAgentOutput(BaseModel):
    """Schedule Agent 输出 Schema"""
    is_deviation: bool  # 是否偏离
    constraint_prompt: str  # 约束提示词（偏离时非空）
    completed_questions: List[str]  # 已完成的问题 ID
    remaining_questions: List[str]  # 待完成的问题 ID
    missing_tool_calls: List[str]  # 遗漏的工具调用
    next_suggested_question: str  # 建议下一个提问

class ScheduleAgent:
    """调度智能体"""
    
    def __init__(
        self, 
        session_id: str,
        task_list: List[QuestionTask],
        llm_client: Any  # LLM 客户端
    ):
        self.session_id = session_id
        self.task_list = task_list
        self.llm_client = llm_client
        self.turn_counter = 0  # 对话轮次计数器
    
    async def evaluate(
        self,
        dialog_history: List[Dict[str, str]],
    ) -> ScheduleAgentOutput:
        """
        评估对话进度并检测偏离
        Args:
            - dialog_history: 对话历史（LangChain格式）
        Return:
            - output: ScheduleAgentOutput
        """
        # 1. 检查对话轮次，每5轮才执行检查
        self.turn_counter += 1
        if self.turn_counter % 5 != 0:
            return self._skip_check()
        
        # 2. 检测对话偏离（调用 LLM）
        is_deviation = await self._check_deviation(dialog_history)
        
        # 3. 检查工具调用完整性
        missing_tools = await self._check_tool_calls(dialog_history)
        
        # 4. 生成约束提示
        constraint_prompt = self._build_constraint_prompt(
            is_deviation, 
            missing_tools
        )
        
        # 5. 统计进度
        completed = self._get_completed_questions(dialog_history)
        remaining = self._get_remaining_questions(completed)
        
        return ScheduleAgentOutput(
            is_deviation=is_deviation or bool(missing_tools),
            constraint_prompt=constraint_prompt,
            completed_questions=completed,
            remaining_questions=remaining,
            missing_tool_calls=missing_tools,
            next_suggested_question=remaining[0] if remaining else ""
        )
    
    async def _check_deviation(
        self, 
        dialog_history: List[Dict[str, str]]
    ) -> bool:
        """
        基于 LLM 判断对话是否偏离
        """
        # TODO: 构建提示词并调用 LLM
        pass
    
    async def _check_tool_calls(
        self, 
        dialog_history: List[Dict[str, str]]
    ) -> List[str]:
        """
        检查是否遗漏工具调用
        例如：患者提到"抽烟"但未调用宣教工具
        """
        pass
```

**验收标准**:
- [x] 能根据量表ID生成完整任务列表
- [x] LLM偏离检测准确率 > 85%（需要提示词调优）
- [x] 工具调用检查无遗漏

---

### 4.3 提示词工程（2-3小时）

**文件位置**: `backend/packages/medagent/agents/service_agent/schedule_agent/prompts.py`

**功能**:
- [x] 设计 system_prompt（定义 Schedule Agent 角色）
- [x] 设计 user_prompt 模板（包含对话历史和任务列表）
- [x] 设计输出 Schema（JSON 格式约束）

**System Prompt 示例**:
```python
SCHEDULE_AGENT_SYSTEM_PROMPT = """
你是一个医疗评估调度助手，负责监控 AI 与患者的对话是否按照量表问题进行。

## 你的职责
1. 判断最近的对话是否偏离了量表问题列表
2. 检查是否遗漏了应该调用的工具（宣教、知情同意书）
3. 给出具体的约束提示，引导 AI 回到正确的评估流程

## 偏离判断标准
- 患者询问与量表无关的问题（例如：食堂在哪里、Wi-Fi密码）
- AI 回答了量表之外的话题
- AI 跳过了必答题
- AI 重复提问已经回答过的问题

## 工具调用检查规则
- 患者提到"抽烟" → 必须调用 get_education_material(category='tobacco')
- 患者提到"喝酒" → 必须调用 get_education_material(category='alcohol')
- 患者提到"手术" → 必须调用 trigger_consent_form(form_type='surgery')
- 患者提到"青霉素过敏" → 必须提醒患者告知医生

## 输出格式
请严格按照 JSON Schema 输出：
{
  "is_deviation": bool,
  "constraint_prompt": str,
  "completed_questions": [str],
  "remaining_questions": [str],
  "missing_tool_calls": [str]
}
"""
```

**User Prompt 模板**:
```python
def build_user_prompt(
    task_list: List[QuestionTask],
    dialog_history: List[Dict[str, str]],
    turn_number: int
) -> str:
    return f"""
## 当前评估任务列表
{json.dumps([t.dict() for t in task_list], ensure_ascii=False, indent=2)}

## 最近的对话历史（最后10轮）
{format_history(dialog_history[-10:])}

## 当前对话轮次
第 {turn_number} 轮

## 请判断
1. AI 是否偏离了量表问题？
2. 是否遗漏了应该调用的工具？
3. 如果偏离，请给出具体的约束提示。
"""
```

**验收标准**:
- [x] 提示词能让 LLM 准确判断偏离
- [x] 输出格式符合 ScheduleAgentOutput Schema
- [x] 准确率通过测试验证（> 85%）

---

### 4.4 Celery 任务封装（2小时）

**文件位置**: `backend/app/celery_app/tasks.py`（已存在，需补充实现）

**功能**:
- [x] 实现 `schedule_agent_worker` 任务
- [x] 订阅 `dialog_stream:{session_id}`
- [x] 每5轮对话触发检查
- [x] 发布 `ConstraintEvent` 到 Redis Stream

**实现代码框架**:
```python
@celery_app.task(name="app.celery_app.tasks.schedule_agent_worker", bind=True)
def schedule_agent_worker(self, session_id: str, task_config: dict):
    """Schedule Agent后台任务
    作用：调度智能体，监控对话进度，检测偏离，注入约束
    Args:
        - session_id: 会话ID
        - task_config: 任务配置（包含量表ID列表等）
    """
    try:
        logger.info(f"[Schedule Agent] 启动任务: session_id={session_id}")
        
        # 1. 加载量表问题列表
        loader = AssessmentQuestionLoader()
        questions = await loader.load_questions_by_form_ids(
            task_config["form_ids"]
        )
        
        # 2. 实例化 Schedule Agent
        agent = ScheduleAgent(
            session_id=session_id,
            task_list=questions,
            llm_client=get_llm_client()  # 使用配置的 LLM
        )
        
        # 3. 订阅 dialog_stream
        redis_client = get_redis()
        stream_key = f"dialog_stream:{session_id}"
        last_id = "0"
        
        while True:
            # 读取新消息
            messages = redis_client.xread(
                {stream_key: last_id},
                count=1,
                block=5000  # 5秒超时
            )
            
            if not messages:
                continue
            
            for stream, msg_list in messages:
                for message_id, data in msg_list:
                    last_id = message_id
                    
                    # 只处理 dialog_turn 事件
                    if data.get("event_type") == "dialog_turn":
                        # 4. 获取对话历史
                        history_manager = DialogHistoryManager()
                        history = await history_manager.get_dialog_history(
                            session_id, limit=20
                        )
                        lc_history = history_manager.format_for_langchain(history)
                        
                        # 5. 执行检查
                        result = await agent.evaluate(lc_history)
                        
                        # 6. 如果偏离，发布约束事件
                        if result.is_deviation:
                            publisher = DialogEventPublisher(session_id)
                            publisher.publish(ConstraintEvent(
                                session_id=session_id,
                                constraint_type="deviation",
                                constraint_prompt=result.constraint_prompt,
                                remaining_tasks=result.remaining_questions
                            ))
                        
                        # 7. 检查是否所有问题完成
                        if not result.remaining_questions:
                            logger.info(f"[Schedule Agent] 所有问题已完成: {session_id}")
                            # 发布会话结束事件
                            publisher.publish(SessionEndEvent(
                                session_id=session_id,
                                end_reason="completed",
                                total_turns=agent.turn_counter
                            ))
                            break
        
        logger.info(f"[Schedule Agent] 任务完成: session_id={session_id}")
        return {"status": "completed", "session_id": session_id}
    
    except Exception as e:
        logger.error(f"[Schedule Agent] 任务失败: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)
```

**验收标准**:
- [x] Celery 任务能正常启动
- [x] 能正确订阅 Redis Stream
- [x] 每5轮对话触发检查
- [x] 约束事件能正确发布

---

### 4.5 单元测试（2-3小时）

**文件位置**: `backend/tests/unit-test/test_schedule_agent.py`

**测试用例**:

```python
import pytest
from app.managers.assessment_loader import AssessmentQuestionLoader
from medagent.agents.service_agent.schedule_agent.agent import (
    ScheduleAgent,
    QuestionTask,
)

class TestAssessmentQuestionLoader:
    """测试量表问题加载器"""
    
    @pytest.mark.asyncio
    async def test_load_questions_by_form_ids(self):
        """测试加载量表问题"""
        loader = AssessmentQuestionLoader()
        questions = await loader.load_questions_by_form_ids(["ADL"])
        
        assert len(questions) > 0
        assert all(not q.derived for q in questions)  # 无计算题
        assert questions[0].sort_no <= questions[-1].sort_no  # 有序
    
    @pytest.mark.asyncio
    async def test_filter_derived_questions(self):
        """测试过滤计算题"""
        loader = AssessmentQuestionLoader()
        questions = await loader.load_questions_by_form_ids(["comprehensive"])
        
        # 验证 BMI 等计算题被过滤
        question_codes = [q.question_code for q in questions]
        assert "BMI" not in question_codes


class TestScheduleAgent:
    """测试 Schedule Agent 核心逻辑"""
    
    @pytest.mark.asyncio
    async def test_deviation_detection_true(self):
        """测试偏离检测（偏离场景）"""
        agent = ScheduleAgent(
            session_id="test_session",
            task_list=[
                QuestionTask(
                    question_id=1,
                    question_code="Q001",
                    patient_text="您是否吸烟？",
                    question_type="single_choice",
                    required=True
                )
            ],
            llm_client=mock_llm_client()
        )
        
        # 模拟偏离对话
        history = [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "我想问一下食堂在哪里"},  # 偏离
        ]
        
        result = await agent.evaluate(history)
        
        assert result.is_deviation is True
        assert "请回到问题" in result.constraint_prompt
    
    @pytest.mark.asyncio
    async def test_deviation_detection_false(self):
        """测试偏离检测（正常场景）"""
        agent = ScheduleAgent(
            session_id="test_session",
            task_list=[
                QuestionTask(
                    question_id=1,
                    question_code="Q001",
                    patient_text="您是否吸烟？",
                    question_type="single_choice",
                    required=True
                )
            ],
            llm_client=mock_llm_client()
        )
        
        # 模拟正常对话
        history = [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "我抽烟，大概每天10支"},
        ]
        
        result = await agent.evaluate(history)
        
        assert result.is_deviation is False
        assert result.constraint_prompt == ""
    
    @pytest.mark.asyncio
    async def test_tool_call_check(self):
        """测试工具调用检查"""
        agent = ScheduleAgent(
            session_id="test_session",
            task_list=[],
            llm_client=mock_llm_client()
        )
        
        # 模拟患者提到抽烟但未调用宣教工具
        history = [
            {"role": "user", "content": "我抽烟"},
            {"role": "assistant", "content": "好的，我知道了"},  # 未调用工具
        ]
        
        result = await agent.evaluate(history)
        
        assert "get_education_material" in result.missing_tool_calls
        assert "tobacco" in result.constraint_prompt
```

**验收标准**:
- [x] 所有测试用例通过
- [x] 覆盖率 > 80%
- [x] 边界场景测试完整

---

## 五、技术难点与解决方案

### 5.1 LLM 偏离检测的准确性

**难点**: LLM 可能误判正常对话为偏离

**解决方案**:
1. 提示词中给出明确的偏离判断标准
2. 提供 few-shot 示例（正常 vs 偏离）
3. 使用更强的模型（例如 qwen-plus）
4. 后期可以引入 RLHF 数据优化

### 5.2 每5轮触发的计数器管理

**难点**: Celery 任务重启后计数器会丢失

**解决方案**:
1. 计数器保存到 Redis: `schedule_agent:turn_counter:{session_id}`
2. 任务启动时从 Redis 读取计数器
3. 每次检查后更新 Redis 中的计数器

### 5.3 长驻 Celery 任务的稳定性

**难点**: 长驻任务可能因网络、Redis 故障中断

**解决方案**:
1. 使用 Celery 的 `bind=True` 和 `retry` 机制
2. Redis 连接失败时自动重连
3. 心跳机制：定期保存检查点到数据库
4. 任务监控：超过10分钟无活动自动告警

---

## 六、开发时间估算

| 任务 | 预计时间 |
|------|----------|
| 4.1 数据层：量表问题加载器 | 1-2小时 |
| 4.2 核心逻辑：Schedule Agent 实现 | 3-4小时 |
| 4.3 提示词工程 | 2-3小时 |
| 4.4 Celery 任务封装 | 2小时 |
| 4.5 单元测试 | 2-3小时 |
| **总计** | **10-14小时（约2个工作日）** |

---

## 七、验收标准

### 7.1 功能验收
- [x] 能根据量表ID生成完整问题列表
- [x] 偏离检测准确率 > 85%
- [x] 工具调用检查无遗漏
- [x] 每5轮对话触发检查
- [x] 约束事件能正确发布到 Redis Stream

### 7.2 性能验收
- [x] LLM 推理延迟 < 3秒
- [x] 任务启动时间 < 1秒
- [x] Redis 订阅延迟 < 100ms

### 7.3 稳定性验收
- [x] Celery 任务能自动重试（最多3次）
- [x] Redis 故障时能降级（记录日志）
- [x] 长驻任务运行 1 小时无异常

---

## 八、后续优化方向

1. **提示词优化**: 收集真实对话数据，持续优化偏离检测提示词
2. **工具调用规则扩展**: 支持更多关键词 → 工具映射
3. **动态调整触发频率**: 根据对话质量动态调整检查频率（3轮 or 5轮 or 10轮）
4. **多模态支持**: 支持语音语气分析（患者是否不耐烦）
5. **A/B测试**: 对比不同 LLM（qwen-plus vs qwen-turbo）的偏离检测效果

---

**创建时间**: 2026-08-17  
**负责人**: AI开发助手  
**状态**: 待审批
