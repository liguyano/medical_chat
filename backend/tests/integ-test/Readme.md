# PostgreSQL 集成测试

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
