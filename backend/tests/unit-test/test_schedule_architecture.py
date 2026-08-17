"""Schedule Agent 分层架构测试。"""

import ast
import subprocess
import sys
from pathlib import Path


def test_medagent_does_not_import_app_package():
    """SDK 层禁止逆向依赖 FastAPI 应用层。"""
    root = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "medagent"
        / "agents"
        / "service_agent"
        / "schedule_agent"
    )
    violations: list[str] = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "app" or name.startswith("app.") for name in names):
                violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_schedule_agent_public_import_works():
    """SDK 公共导入路径必须可用。"""
    from medagent.agents.service_agent.schedule_agent import (
        QuestionTask,
        ScheduleAgent,
        ScheduleAgentOutput,
    )

    assert ScheduleAgent.__name__ == "ScheduleAgent"
    assert QuestionTask.__name__ == "QuestionTask"
    assert ScheduleAgentOutput.__name__ == "ScheduleAgentOutput"


def test_medagent_is_installed_without_pytest_path_injection():
    """后端可编辑安装必须直接提供 medagent 包。"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "from medagent.agents.service_agent.schedule_agent "
                "import ScheduleAgent; print(ScheduleAgent.__name__)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ScheduleAgent"
