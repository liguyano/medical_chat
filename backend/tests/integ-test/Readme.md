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
