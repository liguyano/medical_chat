# PostgreSQL 集成测试

患者管理测试 `test_patient_management.py` 验证省略日期的新建、独立数据库会话查询患者主档与住院记录、编辑保留日期，并在 finally 中清理本次测试记录。
新增同时省略住院号、床号、护理级别和入院来源，核对服务端自动值实际入库及编辑后保留。
同时省略科室、病区、科室编码和医保类别，验证隐藏住院信息区块后的服务端默认与编辑保留。

前置条件：

- Docker 容器 `medical-evaluate-postgres` 正常运行。
- 数据库已执行 `uv run alembic upgrade head`。
- 演示账号登录测试还需 Redis，并先执行 `uv run python -m app.commands.seed_demo`。

默认连接：

```text
postgresql://medical:medical_dev_password@localhost:15432/medical_evaluate
```

可通过环境变量覆盖：

```powershell
$env:TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/database"
uv run pytest tests/integ-test -v
```

CRUD 测试使用外层事务回滚，不保留测试数据。迁移测试创建独立临时数据库，结束后自动删除。

Schedule Agent 与 Dialog Agent 还需要本机 Redis：

```text
localhost:6379/0
```

Docker Desktop 默认容器：

```powershell
docker ps --filter "name=medical-evaluate-postgres"
docker ps --filter "name=medical_redis"
uv run pytest tests/integ-test/test_assessment_catalog_import.py -v
uv run pytest tests/integ-test/test_schedule_agent_redis.py -v
uv run pytest tests/integ-test/test_dialog_agent_redis.py -v
uv run pytest tests/integ-test/test_dialog_agent_postgres.py -v
uv run pytest tests/integ-test/test_demo_account_login.py -v
```

量表导入测试使用 PostgreSQL 外层事务回滚；Redis 测试使用 UUID 临时键并在测试结束时清理。

Dialog Agent 集成测试验证：

- Schedule `ConstraintEvent` 只注入一次并持久化消费游标；
- Dialog 轮次/工具事件符合 Schedule runner 的统一 Stream 契约；
- 活动时间戳 TTL 与结束清理；
- 一轮真实 PostgreSQL 患者/AI 消息同轮持久化。

完整验收还需启动 Windows `solo` Celery worker，向 `schedule_queue` 或
`dialog_queue` 提交一个不存在量表编码的烟测任务。预期 worker 完成数据库和
Redis 初始化、查询真实 PostgreSQL，并返回
`{"status": "failed", "reason": "no_questions_loaded"}`；
烟测配置、Redis 结果键和 worker 进程必须在验证后清理。
# 人工题回归（2026-09-15）

数据库与迁移就绪后，在 backend 执行 `uv run --extra dev pytest tests/integ-test/test_manual_questions.py -q`。
使用公共 `postgres_session_factory` 的外层事务回滚，不保留演示数据。覆盖题库标记保存、AI/旧缓存跳题、人工题只读、患者进度、全人工任务、人工计分缺失与护士最终复核。后台派发替身不调用模型或呼叫护士。

### 真实语音话题试验

`test_actual_voice_topics.py` 需显式设置 `RUN_ACTUAL_VOICE=1`、`SYNTHETIC_VOICE_DIR`（0.wav至5.wav，16kHz单声道PCM16）及可选 `TOPIC_ROUTE_PLAN_FILE`。使用当前配置的真实语音供应商与虚构音频，必须先获得外发授权。测试模拟缺项工具结果，不连接患者数据库，属于供应商集成验证，不能算完整业务E2E。2026-10-27六轮均有真实ASR及音频，最后通话确认后追加问题断言失败，保留失败作为改进依据。

2026-10-28初判试验：真实语音集成脚本支持mark_patient_response_heard，并等待真实ASR后校验引用。提取结果模拟，不能冒充业务E2E；最新合成多轮仍有重复追问与通话确认追加问题，效果断言未通过。

2026-10-29语音减负：当前脚本只要求真实六轮ASR/音频及仅结束核验工具，不再强制旧话题模板和初判工具。简版真实合成测试通过，明确进食动作后转睡眠；部分回答不足时仍会追问，此通过不代表所有重复问题或自然度已解决。后台提取仍为测试模拟。
