"""Extraction Agent 完成后异步触发 Dialog Exit 的测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.celery_app.tasks import extraction_agent_worker
from app.configs.app_config import ModelConfig


def test_completed_progress_dispatches_dialog_completion(monkeypatch):
    """Extraction 完成只派发结束任务，不在当前 Worker 阻塞等待 Dialog。"""
    from medagent import providers

    from app import configs, utils
    from app.celery_app import runtime, tasks
    from app.workers import extraction_agent_runner as runner_module

    model_config = ModelConfig(
        name="qwen",
        display_name="qwen",
        model="qwen",
        api_base="https://example.com/v1",
        api_key="key",
    )
    monkeypatch.setattr(
        configs.app_config,
        "get_app_config",
        lambda: SimpleNamespace(get_agent_model_config=lambda _: model_config),
    )
    monkeypatch.setattr(providers, "create_chat_model", Mock(return_value=object()))
    monkeypatch.setattr(runtime, "ensure_worker_runtime", Mock())
    monkeypatch.setattr(utils.redis_client, "get_redis", Mock(return_value=object()))
    runner = SimpleNamespace(
        run=AsyncMock(
            return_value={
                "status": "turn_completed",
                "assessment_completed": True,
            }
        )
    )
    monkeypatch.setattr(
        runner_module,
        "ExtractionAgentRunner",
        Mock(return_value=runner),
    )
    completion_delay = Mock()
    monkeypatch.setattr(tasks.dialog_agent_worker, "delay", completion_delay)

    result = extraction_agent_worker.run(
        "SESS-1",
        {
            "scale_codes": ["scale"],
            "source_message_id": "PATIENT-1",
            "patient_info": {"name": "患者"},
        },
    )

    assert result["assessment_completed"] is True
    completion_delay.assert_called_once()
    assert completion_delay.call_args.args[2]["finalize"] is True
