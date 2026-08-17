# 步骤4：Schedule Agent 完整测试计划

## 1. 测试目标

验证 Schedule Agent 从量表目录、数据库加载、智能体判断、Redis Stream 编排、
Celery worker 到真实 OpenAI 兼容模型调用的完整链路，确保其满足以下要求：

- 每 5 轮对话触发一次语义检查；
- 正确维护已完成问题和剩余问题；
- 正确识别对话偏离、合理追问、共情、宣教和重复提问；
- 基于真实 `tool_calls` 检查宣教工具完整性；
- Redis Stream 事件可解码、可发布并支持检查点恢复；
- 独立 Celery worker 能初始化 PostgreSQL 与 Redis；
- 量表目录可幂等导入，未审核量表不得自动发布；
- 真实模型语义判断准确率严格大于 85%。

## 2. 测试边界

本计划仅覆盖步骤4及其直接依赖，不开发步骤5 Dialog Agent。

以下内容不属于本次测试失败项：

- 步骤9才实现的任务启动、查询和停止 API；
- Schedule Agent 与尚未实现的 Dialog Agent 联调；
- 临床专家对量表内容的发布审批；
- 生产容量压测和多 worker 集群压测。

## 3. 测试环境

- [X] Windows 11、PowerShell、Python 3.11
- [X] pytest、pytest-asyncio、pytest-cov
- [X] Docker PostgreSQL 16：`localhost:15432`
- [X] Docker Redis 7：`localhost:6379`
- [X] Celery 5，Windows `solo` worker
- [X] 阿里云百炼 OpenAI 兼容接口，真实 `qwen-plus`
- [X] 独立 Git worktree：`medical-evaluate-schedule-agent-test`
- [X] 独立分支：`test/schedule-agent`

## 4. 单元测试

### 4.1 SDK 核心

- [X] QuestionTask、QuestionOption、ToolCallRecord 与输出 Schema 校验
- [X] 未到第 5 轮时跳过 LLM 检查
- [X] 第 5 轮及其倍数触发检查
- [X] LLM JSON 结构化响应解析
- [X] 已完成问题累积与剩余问题更新
- [X] 智能体状态 dump/restore
- [X] LLM 异常和非法 JSON 时 fail-open
- [X] 真实工具名称、参数和缺失工具检查
- [X] “不吸烟”等否定语义不触发戒烟工具
- [X] 损坏工具调用记录安全降级

对应文件：

- `backend/tests/unit-test/test_schedule_agent.py`
- `backend/tests/unit-test/test_schedule_agent_prompts.py`

### 4.2 App 编排与配置

- [X] OpenAI 兼容模型列表和 Agent 模型绑定
- [X] `$ENV`、`${ENV}` 密钥引用解析
- [X] 模型缺失时明确失败
- [X] Celery 任务组装、重试与运行参数透传
- [X] Celery 运行时按 PID 幂等初始化
- [X] prefork PID 变化后重新初始化基础设施
- [X] Redis bytes/JSON 字段解码
- [X] 约束事件与会话结束事件发布
- [X] 检查点保存失败触发任务重试
- [X] `medagent` 不逆向导入 `app.*`
- [X] 安装后的 wheel 可直接导入 `medagent`

对应文件：

- `backend/tests/unit-test/test_schedule_config.py`
- `backend/tests/unit-test/test_schedule_agent_celery.py`
- `backend/tests/unit-test/test_celery_runtime.py`
- `backend/tests/unit-test/test_schedule_agent_runner.py`
- `backend/tests/unit-test/test_schedule_architecture.py`

### 4.3 量表导入

- [X] 真实目录结构解析
- [X] 量表、版本、分组、问题、选项、规则和动作映射
- [X] 导入幂等
- [X] `pending_review` 保持“审核中”
- [X] 派生题标记和问题选项完整性

对应文件：

- `backend/tests/unit-test/test_assessment_catalog_importer.py`

## 5. 集成测试

- [X] 真实 PostgreSQL 量表目录导入，事务回滚后无残留
- [X] 真实 PostgreSQL 领域持久化回归
- [X] 真实 Redis Stream bytes 事件消费
- [X] ConstraintEvent 往返序列化
- [X] Alembic 独立临时数据库 upgrade/check/downgrade
- [X] 开发库真实量表首次导入
- [X] 开发库真实量表二次导入新增数为 0
- [X] 开发库保持 5 个“审核中”量表版本，不擅自发布

对应文件：

- `backend/tests/integ-test/test_assessment_catalog_import.py`
- `backend/tests/integ-test/test_schedule_agent_redis.py`
- `backend/tests/integ-test/test_domain_persistence.py`
- `backend/tests/integ-test/test_alembic_migration.py`

## 6. 真实 Celery worker 烟测

- [X] 启动 Windows `solo` worker
- [X] 注册 `schedule_queue` 与 Schedule Agent 任务
- [X] worker 进程初始化 Redis
- [X] Schedule Agent 任务连接真实 PostgreSQL
- [X] 提交不存在量表编码并返回 `no_questions_loaded`
- [X] 验证任务结果进入 Celery backend
- [X] 停止烟测 worker
- [X] 清理临时配置和已知烟测结果键

## 7. 真实模型 E2E

- [X] 使用真实 `DASHSCOPE_API_KEY`
- [X] 通过 OpenAI 兼容接口调用 `qwen-plus`
- [X] 覆盖不吸烟、正常追问、共情、宣教、拉回评估、明显偏离、重复提问
- [X] 7 类场景准确率严格大于 85%
- [X] 未配置密钥时明确 skip，不使用伪模型冒充 E2E

对应文件：

- `backend/tests/e2e-test/test_schedule_agent_llm.py`

## 8. 静态质量与覆盖率

- [X] Ruff 检查通过
- [X] Mypy 检查通过
- [X] Python `compileall` 通过
- [X] `git diff --check` 无空白错误
- [X] 步骤4目标模块综合覆盖率 96%，高于 80% 门槛

## 9. 验收结果

- [X] 单元测试：72 passed
- [X] 集成测试：10 passed
- [X] 真实模型 E2E：1 passed
- [X] 最终统一回归：83 passed
- [X] 综合覆盖率：96%
- [X] 真实 Celery worker 烟测通过
- [X] 未发现测试数据残留
- [X] 测试报告已生成

## 10. 执行命令

在 `backend` 目录执行：

```powershell
uv run pytest tests/unit-test -q
uv run pytest tests/integ-test -q
uv run pytest tests/e2e-test -q
uv run pytest tests/unit-test tests/integ-test tests/e2e-test -q
```

覆盖率：

```powershell
uv run pytest tests/unit-test tests/integ-test tests/e2e-test -q `
  --cov=medagent.agents.service_agent.schedule_agent `
  --cov=app.managers.assessment_loader `
  --cov=app.managers.assessment_catalog_importer `
  --cov=app.workers.schedule_agent_runner `
  --cov=app.celery_app.runtime `
  --cov=app.configs.app_config `
  --cov-report=term
```

---

**创建时间**：2026-08-17
**最后更新**：2026-08-17
**状态**：已完成
