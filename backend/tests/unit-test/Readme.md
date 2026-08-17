# 单元测试

在 `backend` 目录执行：

```powershell
uv run pytest tests/unit-test -v
```

本目录测试不得连接 PostgreSQL、Redis 或外部模型；外部依赖必须使用 fake/mock/stub。
