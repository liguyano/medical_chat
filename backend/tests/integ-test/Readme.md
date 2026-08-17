# PostgreSQL 集成测试

前置条件：

- Docker 容器 `medical-evaluate-postgres` 正常运行。
- 数据库已执行 `uv run alembic upgrade head`。

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

Schedule Agent 还需要本机 Redis：

```text
localhost:6379/0
```

Docker Desktop 默认容器：

```powershell
docker ps --filter "name=medical-evaluate-postgres"
docker ps --filter "name=medical_redis"
uv run pytest tests/integ-test/test_assessment_catalog_import.py -v
uv run pytest tests/integ-test/test_schedule_agent_redis.py -v
```

量表导入测试使用 PostgreSQL 外层事务回滚；Redis 测试使用 UUID 临时键并在测试结束时清理。

完整验收还需启动 Windows `solo` Celery worker，向 `schedule_queue` 提交一个
不存在量表编码的烟测任务。预期 worker 完成数据库和 Redis 初始化、查询真实
PostgreSQL，并返回 `{"status": "failed", "reason": "no_questions_loaded"}`；
烟测配置、Redis 结果键和 worker 进程必须在验证后清理。
