# 步骤6 - Field Extraction Agent（字段抽取智能体）开发计划

## 项目信息
- **需求名称**: 入院量表评估 - AI对话方案（Field Extraction Agent）
- **上游依赖**: 步骤1-5 已完成（基础设施、Redis Stream、状态管理、Schedule Agent、Dialog Agent）
- **设计来源**:
  - `docs/后端详细设计方案.md`（extract_with_retry 骨架）
  - `docs/需求1-入院量表评估.md`（字段抽取准确率要求）
  - `docs/sql/数据库表业务设计.md`（assessment_answer 表结构）
  - `docs/structured/assessment-scales/*.json`（量表字段类型）
- **开始时间**: 2026-08-17
- **预计工期**: 1-2 天

---

## 一、开发前技术决策（待用户确认）

| # | 决策项 | 最终方案 | 备注 |
|---|-------|---------|------|
| 1 | 抽取触发时机 | ✅ **每轮立即抽取** | 实时性优先，护士可随时查看进度 |
| 2 | 历史分析范围 | ✅ **增量+摘要方案** | `历史抽取字段 + 历史对话摘要(2-3句话) + 新对话` |
| 3 | 低置信度处理 | ✅ **自动标记 needs_review=True** | 前端高亮 `extraction_confidence < 0.6` 的字段 |
| 4 | 派生字段计算 | ✅ **Agent 内计算** | LLM 直接计算 BMI/体重下降比例 |
| 5 | 前端更新策略 | ✅ **增量 merge** | 检查 `value_source`，若为 `nurse_corrected` 则跳过不覆盖 |

### 关键现状说明
- `assessment_execution.py` ORM 已完整落地 6 张表（submission/answer/answer_option/score/review/rating）
- `DialogHistoryManager` 已实现 `get_recent_messages(limit)` 和 `format_for_llm()`
- `AssessmentQuestionLoader` 已实现 `load_questions_by_scale_codes()`
- `config.yaml` 已配置 `extraction_agent: qwen-plus` （temperature: 0.1）
- `app/schemas/events.py` 已定义 `ExtractionResultEvent`

### 决策2 技术细节（增量+摘要方案）

**输入构成**：
```python
prompt_input = {
    "previous_extraction": {  # 历史抽取字段
        "question_101": {"answer": "吸烟", "confidence": 0.90, "source_turns": [5, 6]},
        "question_102": {"answer": 65.0, "unit": "kg", "confidence": 0.95}
    },
    "history_summary": "患者自述吸烟20年史，每天约15支；体重65公斤，身高175cm。",  # 2-3句话压缩
    "new_dialog": [  # 当前轮新对话
        {"turn": 8, "patient": "最近戒烟了，现在不抽了", "ai": "很好！什么时候开始戒的？"}
    ]
}
```

**优势**：
- Token 节省：避免每次重传全部 20 轮对话（约 4000 tokens → 压缩到 500 tokens）
- 上下文保留：摘要保持语义关联（如"吸烟20年史"关联到后续"戒烟"）
- 修正支持：新对话可纠正历史字段（confidence 降低 → 触发覆盖）

**实现要点**：
1. `DialogHistoryManager` 新增 `summarize_history(messages) -> str` 方法（调用 LLM，temperature=0.3）
2. `ExtractionResultWriter` 新增 `get_previous_extraction(submission_id) -> dict` 方法（读取上次结果）
3. 提示词模板新增 `previous_extraction` 和 `history_summary` 占位符

---

## 二、目录结构规划

```
backend/packages/medagent/agents/
├── service_agent/
│   └── extraction_agent/
│       ├── __init__.py           # 导出 FieldExtractionAgent
│       ├── agent.py              # 核心抽取逻辑 + 重试机制
│       ├── prompt.py             # system_prompt 构建 + Few-shot 示例
│       └── validator.py          # JSON Schema 校验器

backend/app/
├── workers/
│   └── extraction_agent_runner.py  # Celery 任务编排（类比 schedule_agent_runner.py）
└── managers/
    └── extraction_result_writer.py  # ORM 写入封装（upsert submission/answer/score）
```

> 说明：沿用 medagent 层放置（与 schedule_agent/dialog_agent 一致）；extraction_agent/ 禁止 import app；应用编排层（runner/writer）允许 import medagent。

---

## 三、开发子步骤

### 6.1 核心逻辑实现（`agent.py`）
- [ ] 定义 `FieldExtractionAgent` 类：`__init__(session_id, scale_codes, llm_client, model_config)`
- [ ] `extract_from_dialog(previous_extraction, history_summary, new_dialog, scale_version, questions)` 主方法：
  - [ ] 构建 system_prompt（调用 prompt.py）
  - [ ] 构建 user_prompt（整合历史抽取字段 + 对话摘要 + 新对话）
  - [ ] 调用 LLM（temperature=0.1，response_format=json_object）
  - [ ] 返回结构化结果：`{"extracted_answers": [...], "overall_confidence": 0.85, "missing_questions": [], "ambiguous_questions": []}`
- [ ] `extract_with_retry(max_retries=3)` 重试封装：
  - [ ] 捕获 `ValidationError`（JSON 格式/Schema 校验失败）
  - [ ] 捕获 `openai.APITimeoutError`（LLM 超时）
  - [ ] 最后一次失败时调用 `_mark_manual_intervention()`
- [ ] `_calculate_derived_fields(answers)` 派生字段计算：
  - [ ] BMI = weight_kg / (height_m ** 2)
  - [ ] 体重下降比例 = (usual_weight - current_weight) / usual_weight
  - [ ] 血压分类（正常/偏高/高血压）

### 6.2 提示词工程（`prompt.py`）
- [ ] `build_system_prompt(scale_version, questions)` 模板：
  - [ ] 核心原则：忠实原文/多轮综合/置信度标注/来源追溯
  - [ ] 量表信息：scale_name, version_code
  - [ ] 问题定义（JSON Schema）：question_id, question_code, answer_type, options, scoring_rules
  - [ ] 输出格式（严格 JSON Schema）
- [ ] `build_user_prompt(previous_extraction, history_summary, new_dialog)` 构建输入：
  - [ ] **历史抽取字段**：`question_id -> {answer, confidence, source_turns}`
  - [ ] **历史对话摘要**：2-3句话压缩（保持上下文语义）
  - [ ] **新对话**：`[轮次{turn_number}] 患者：{question} → AI：{answer}`
  - [ ] 提示：**如果新对话纠正了历史字段，请更新并降低置信度；如果无关则复用历史字段**
- [ ] `summarize_dialog_history(messages)` 对话摘要生成：
  - [ ] 调用 LLM（temperature=0.3）
  - [ ] 提示词：将以下对话压缩为2-3句话，保留关键医疗信息（症状/药物/数值）
  - [ ] 输出示例：`"患者自述吸烟20年史，每天约15支；体重65公斤，身高175cm；否认药物过敏。"`
- [ ] Few-shot 示例库（`examples.py`）：
  - [ ] 文本字段：`"患者说：我叫张三" → {"answer_text": "张三", "confidence": 0.95}`
  - [ ] 数值字段：`"患者说：体重65公斤" → {"answer_number": 65.0, "answer_unit": "kg", "confidence": 0.92}`
  - [ ] 布尔字段：`"患者说：没有过敏" → {"answer_boolean": False, "confidence": 0.98}`
  - [ ] 单选字段：`"患者说：我抽烟" → {"selected_option_codes": ["smoking_yes"], "clinical_score": 2.0, "confidence": 0.90}`
  - [ ] 多选字段：`"患者说：我有糖尿病和高血压" → {"selected_option_codes": ["diabetes", "hypertension"], "confidence": 0.95}`
  - [ ] 附加输入：`"患者说：吸烟20年，每天15支" → {"extra_inputs": {"years": 20, "frequency": 15, "unit": "支/天"}, "confidence": 0.88}`
  - [ ] **增量纠正**：`历史："吸烟，15支/天"(confidence=0.90) + 新对话："最近戒烟了" → {"selected": ["smoking_no"], "extra": {"quit_date": "近期"}, "confidence": 0.75, "reasoning": "患者纠正历史信息"}`
  - [ ] **增量补充**：`历史："吸烟"(confidence=0.85) + 新对话："每天大概15支" → {"selected": ["smoking_yes"], "extra": {"frequency": 15, "unit": "支/天"}, "confidence": 0.92, "source_message_ids": [5, 6]}`
  - [ ] 低置信度：`[轮8] 患者：嗯...差不多吧 → {"confidence": 0.45, "reasoning": "回答模糊，需护士确认"}`

### 6.3 JSON Schema 校验（`validator.py`）
- [ ] 定义 Pydantic 模型 `ExtractionResult`：
  ```python
  class ExtractedAnswer(BaseModel):
      question_id: int
      question_code: str
      answer_type: Literal["text", "number", "boolean", "date", "single_choice", "multiple_choice"]
      answer_value: str | float | bool | date | None
      selected_option_codes: list[str] = []
      extra_inputs: dict[str, Any] = {}
      clinical_score: float | None
      extraction_confidence: float  # 0.0-1.0
      source_message_ids: list[int]
      reasoning: str
  
  class ExtractionResult(BaseModel):
      extracted_answers: list[ExtractedAnswer]
      overall_confidence: float
      missing_questions: list[int]
      ambiguous_questions: list[int]
  ```
- [ ] `validate_extraction_result(raw_json: dict) -> ExtractionResult`：
  - [ ] Pydantic 自动校验 + 返回类型化对象
  - [ ] 校验失败抛出 `ValidationError`

### 6.4 ORM 写入封装（`app/managers/extraction_result_writer.py`）
- [ ] `ExtractionResultWriter` 类（纯应用层，可 import app.models）
- [ ] `get_previous_extraction(submission_id) -> dict` 读取上次抽取结果：
  - [ ] 查询 `assessment_answer` 表（where submission_id）
  - [ ] 返回格式：`{"question_id": {"answer": "...", "confidence": 0.90, "source_turns": [5, 6]}}`
- [ ] `upsert_submission(session_id, extraction_result) -> AssessmentSubmission`：
  - [ ] 首次创建 or 更新已有 AI submission（`submission_type='ai_extraction'`）
  - [ ] 计算 `answered_question_count` / `total_question_count`
  - [ ] 更新 `confidence_score`（overall_confidence）
  - [ ] 更新 `submission_status`（in_progress / completed）
- [ ] `upsert_answers(submission_id, extracted_answers) -> list[AssessmentAnswer]`：
  - [ ] **增量 merge 逻辑**：检查 `value_source`，若为 `nurse_corrected` 则跳过该题不覆盖
  - [ ] 唯一约束 `(submission_id, question_id)` → ON CONFLICT UPDATE
  - [ ] 写入 answer_text / answer_number / answer_boolean / answer_date
  - [ ] 写入 extraction_confidence / source_message_ids（JSONB 数组）
  - [ ] 设置 value_source='ai_extracted'（仅 AI 首次抽取或更新时）
- [ ] `upsert_answer_options(answer_id, selected_options) -> list[AssessmentAnswerOption]`：
  - [ ] 单选/多选题写入选项明细表
  - [ ] 记录 option_code_snapshot / option_label_snapshot
  - [ ] 记录 extra_text / extra_number / extra_unit（"其他"补充）
- [ ] `calculate_scores(submission_id, scale_version_id) -> list[AssessmentScore]`：
  - [ ] 从 scale_version 加载 scoring_rules（JSONB）
  - [ ] 汇总 clinical_score → total_score
  - [ ] 计算 risk_level（根据阈值）
  - [ ] 记录 calculation_detail（JSONB）

### 6.5 Celery 任务编排（`app/workers/extraction_agent_runner.py`）
- [ ] `ExtractionAgentRunner` 类（类比 `ScheduleAgentRunner`）
- [ ] `run(session_id, check_interval=5)` 主循环：
  - [ ] 订阅 `dialog_stream:{session_id}`（XREAD BLOCK）
  - [ ] 消费 `DialogTurnEvent`
  - [ ] **读取历史抽取字段**：调用 `writer.get_previous_extraction(submission_id)`
  - [ ] **生成对话摘要**：调用 `history_manager.summarize_history(old_messages)` 或 读取 Redis 缓存的摘要
  - [ ] **获取新对话**：当前轮 DialogTurnEvent 内容
  - [ ] 调用 `FieldExtractionAgent.extract_with_retry(previous_extraction, history_summary, new_dialog)`
  - [ ] 调用 `ExtractionResultWriter.upsert_*()` 写库
  - [ ] **更新摘要缓存**：将当前轮追加到摘要（或重新生成）
  - [ ] 发布 `ExtractionResultEvent` 到 `extraction_result_stream:{session_id}`
  - [ ] 检查完成度：`answered_question_count == total_question_count` → 发布 `ExtractionCompleteEvent`
- [ ] 错误处理：
  - [ ] 重试 3 次失败 → 更新 `care_task.need_manual_intervention=True`
  - [ ] 记录 `intervention_reason="AI字段抽取失败，需人工补录"`

### 6.6 Celery 任务封装（`app/celery_app/tasks.py`）
- [ ] 完善 `extraction_agent_worker(self, session_id, task_config)` 任务：
  ```python
  @celery_app.task(name="app.celery_app.tasks.extraction_agent_worker", bind=True)
  def extraction_agent_worker(self, session_id: str, task_config: dict):
      """Field Extraction Agent 后台任务"""
      config = get_app_config()
      model_config = config.get_agent_model_config("extraction_agent")
      
      client = AsyncOpenAI(
          api_key=model_config.resolved_api_key(),
          base_url=model_config.api_base,
          timeout=model_config.timeout,
      )
      
      runner = ExtractionAgentRunner(
          loader=AssessmentQuestionLoader(),
          history_manager=DialogHistoryManager(),
          writer_factory=ExtractionResultWriter,
          redis_client=get_redis(),
          publisher_factory=DialogEventPublisher,
          llm_client=client,
          model_config=model_config,
      )
      
      return asyncio.run(
          runner.run(
              session_id,
              scale_codes=task_config.get("scale_codes", []),
              check_interval=task_config.get("check_interval", 5),
          )
      )
  ```

---

## 四、验收标准（本步骤，不含测试执行）

- [ ] 提示词符合"忠实原文/多轮综合/置信度标注/来源追溯"四大原则
- [ ] Few-shot 覆盖 8 种字段类型（text/number/boolean/date/single_choice/multiple_choice/附加输入/多轮综合）
- [ ] JSON Schema 校验完整，格式错误能触发重试
- [ ] 最多重试 3 次，失败后正确标记 `need_manual_intervention=True`
- [ ] ORM 写入符合唯一约束 `(submission_id, question_id)`，支持 upsert
- [ ] 派生字段（BMI/体重下降比例）计算准确
- [ ] 临床得分汇总正确，risk_level 分类符合规则
- [ ] 每轮对话后发布 `ExtractionResultEvent`，SSE 可推送前端
- [ ] 全部字段抽取完成后发布 `ExtractionCompleteEvent`
- [ ] 代码通过 Ruff 静态检查

> **测试**：按项目约定，本步骤**不开发测试**。核心开发完成后编写《步骤6-FieldExtractionAgent测试计划》文档，测试执行由 `test/*` 分支独立进行。

---

## 五、与其他 Agent 的协作关系

```
Dialog Agent → 发布 DialogTurnEvent → Redis Stream (dialog_stream:{session_id})
                                           ↓
                              Field Extraction Agent 订阅消费
                                           ↓
                              写入 PostgreSQL (assessment_answer 表)
                                           ↓
                              发布 ExtractionResultEvent → SSE 推送服务 → 前端实时更新
                                           ↓
                              Schedule Agent 读取进度 (answered_question_count / total_question_count)
                                           ↓
                              判断是否需要干预 Dialog Agent（发布 ConstraintEvent）
```

**关键契约**：
- **输入事件**：`DialogTurnEvent`（来自 Dialog Agent）
- **输出事件**：`ExtractionResultEvent`（推送护士端）、`ExtractionCompleteEvent`（通知 Schedule Agent）
- **状态存储**：PostgreSQL `assessment_submission` / `assessment_answer` 表（持久化，Schedule Agent 可查询）
- **幂等性**：同一 `(submission_id, question_id)` 多次抽取时覆盖更新（upsert），保留最新置信度

---

## 六、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| LLM 温度 0.1 仍不稳定，同样输入抽取结果不一致 | 高 | 提示词强化"忠实原文"约束；Few-shot 补充边界 case；考虑改用 temperature=0（完全确定性） |
| 对话摘要丢失关键信息（如追问细节） | 高 | 摘要提示词强调保留"数值/药物/症状"关键词；提供摘要质量 Few-shot 示例 |
| 增量纠正逻辑误判（患者补充被当成纠正） | 中 | 提示词明确"纠正 vs 补充"判断标准：纠正=矛盾（"不抽烟了"），补充=细化（"每天15支"） |
| 历史抽取字段 + 摘要 + 新对话总 token 仍超限 | 中 | 动态裁剪：优先保留低置信度字段；摘要压缩到 1 句话；新对话最多 3 轮 |
| 护士修正答案后，AI 下一轮重新抽取又覆盖 | 高 | **增量 merge**：检查 `value_source`，若为 `nurse_corrected` 则跳过该题不覆盖 |
| 对话摘要生成调用 LLM 增加延迟（额外 1-2 秒） | 中 | Redis 缓存摘要（TTL=1小时）；仅当历史对话变化时重新生成 |
| 派生字段计算错误（如 BMI 单位换算） | 中 | 单元测试覆盖计算逻辑；提示词给出单位换算示例 |

---

## 七、交付物清单

1. `extraction_agent/agent.py`、`prompt.py`、`validator.py`、`__init__.py`
2. `app/workers/extraction_agent_runner.py`
3. `app/managers/extraction_result_writer.py`
4. `app/celery_app/tasks.py` 的 `extraction_agent_worker` 完善
5. `docs/plan/需求1-后端开发计划.md` 步骤6 勾选更新
6. 《步骤6-FieldExtractionAgent测试计划》文档（开发完成后）

---

## 八、新增依赖与配置

### 8.1 DialogHistoryManager 扩展
- [ ] `app/managers/dialog_history_manager.py` 新增方法：
  ```python
  async def summarize_history(
      self, 
      session_id: str, 
      llm_client: AsyncOpenAI,
      max_turns: int = 20
  ) -> str:
      """生成对话摘要（2-3句话）
      作用：压缩历史对话，保留关键医疗信息
      Args:
          - session_id: 会话ID
          - llm_client: LLM 客户端
          - max_turns: 最多摘要多少轮对话
      Return:
          - 摘要文本（2-3句话）
      """
      messages = await self.get_recent_messages(session_id, limit=max_turns)
      # ... 调用 LLM 生成摘要
  ```

### 8.2 Redis 摘要缓存
- [ ] 缓存键：`dialog_summary:{session_id}`
- [ ] TTL：1 小时
- [ ] 更新策略：每轮对话后追加当前轮到摘要（或超过 5 轮后重新生成）

### 8.3 配置文件校验
- [ ] `config.yaml` 确认 `extraction_agent` 配置：
  ```yaml
  agent_models:
    extraction_agent: qwen-plus
  
  models:
    - name: qwen-plus
      temperature: 0.1  # 低温保证一致性
      max_retries: 2
      timeout: 30.0
  ```

---

## 九、待用户确认的 5 个关键决策（已确认）

---

**创建时间**: 2026-08-17  
**负责人**: AI开发助手  
**状态**: ✅ 技术决策已确认，准备创建 `feat/extraction-agent` 分支开发
