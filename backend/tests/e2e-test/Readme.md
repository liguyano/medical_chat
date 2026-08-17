# Schedule Agent 端到端测试

在 `backend` 目录执行：

```powershell
$env:DASHSCOPE_API_KEY = "真实密钥"
uv run pytest tests/e2e-test -v
```

测试会通过阿里云百炼的 OpenAI 兼容接口真实调用 `qwen-plus`，用于验证偏离检测准确率。未配置 `DASHSCOPE_API_KEY` 时测试会明确跳过，不会伪造端到端结果。
