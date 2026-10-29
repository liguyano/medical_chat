# 智能体真实模型端到端测试

在 `backend` 目录执行：

```powershell
$env:DASHSCOPE_API_KEY = "真实密钥"
uv run pytest tests/e2e-test -v
```

测试会通过阿里云百炼的 OpenAI 兼容接口真实调用 `qwen-plus`：

- Schedule Agent：验证七类偏离检测场景，准确率必须超过 85%。
- Dialog Agent：验证系统提示词、真实患者文本输入、模型流式输出和完整一轮编排。

可用以下变量覆盖 Dialog Agent 的测试模型：

```powershell
$env:DIALOG_TEST_MODEL = "qwen-plus"
$env:DIALOG_TEST_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

未配置 `DASHSCOPE_API_KEY` 时测试会明确跳过，不会伪造端到端结果。

豆包全双工语音 E2E 还需要真实 API Key、App ID、Resource ID 和与当前事件协议匹配的
WebSocket endpoint。条件不完整时禁止使用 Fake WebSocket 冒充真实语音 E2E。

### 任务话题路线生成

显式设置 `RUN_TOPIC_LLM=1` 后运行 `test_task_topic_route_llm.py`，使用当前 Schedule 模型及虚构题目，需先获模型外发授权。可选 `TOPIC_ROUTE_PLAN_OUT` 保存合成路线。只验证真实路线生成，不证明真实语音对话效果。
