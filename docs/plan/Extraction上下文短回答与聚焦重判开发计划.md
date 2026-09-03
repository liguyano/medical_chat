# Extraction 上下文短回答与聚焦重判开发计划

> **执行要求：** 按测试驱动开发逐项执行；每个行为先写失败测试，再写最小实现。

## 1. 需求与边界

- [X] 1.1 确认语义判断交给 Extraction AI，后端不把“没有”“不会”等词硬编码为固定答案。
- [X] 1.2 确认模型输出继续使用 `RawExtractionResult` JSON Schema，后端校验题目归属、选项和值类型。
- [X] 1.3 确认首次没有形成有效答案时，只围绕实际问句和当前题目执行一次聚焦重判。
- [X] 1.4 确认聚焦重判仍无有效答案时不写数据库，由后续对话自然澄清。

## 2. Extraction 提示词与结构化重判

涉及文件：

- `backend/packages/medagent/agents/service_agent/extraction_agent/prompt.py`
- `backend/packages/medagent/agents/service_agent/extraction_agent/agent.py`
- `backend/tests/unit-test/test_extraction_contract.py`

- [X] 2.1 编写失败测试：系统提示词要求结合实际问句、量表题目和选项语义理解短回答，并包含“通道能顺畅通行吗 + 没问题啊”的少量示例。
- [X] 2.2 编写失败测试：首次返回空答案后仅调用一次聚焦重判，并继续使用 `RawExtractionResult` 结构化输出。
- [X] 2.3 编写失败测试：首次已有有效答案时不触发聚焦重判；二次仍为空时保持空结果。
- [X] 2.4 实现上下文短回答提示词和单次聚焦重判，保持既有 JSON Schema 与后端候选校验不变。
- [X] 2.5 运行 Extraction 单元测试并确认通过。

## 3. 当前题目关联与重判范围

涉及文件：

- `backend/app/workers/extraction_agent_runner.py`
- `backend/tests/unit-test/test_extraction_agent_runner_values.py`

- [X] 3.1 编写失败测试：Extraction Runner 优先使用患者消息或对应 AI 消息的 `related_question_id` 限定聚焦题目。
- [X] 3.2 编写失败测试：语音消息原先没有题目关联时，Extraction 形成唯一有效答案后回填患者消息和对应 AI 消息的 `related_question_id`。
- [X] 3.3 实现题目关联透传与抽取后回填；一轮涉及多个题目或无法确定时保留空值，不用关键词猜测题号。
- [X] 3.4 运行 Runner 单元测试并确认通过。

## 4. 回归验证与文档同步

- [X] 4.1 更新 `backend/AGENTS.md`，记录上下文短回答由 AI 判断、后端结构化校验和单次聚焦重判边界。
- [X] 4.2 运行本次范围相关 Extraction、Dialog Runner、Voice Gateway 测试；另确认既存 Dialog 工具注册测试仍有 1 项失败，不纳入本次修改。
- [X] 4.3 执行 Python 编译检查和差异检查，确认未覆盖工作区原有修改。
- [X] 4.4 本任务未启动前后端服务，无新增后台进程需要停止。
