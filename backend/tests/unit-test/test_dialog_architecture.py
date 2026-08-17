"""Dialog Agent 公共导入与分层边界测试。"""

import ast
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = BACKEND_ROOT / "packages" / "medagent" / "agents"


def test_dialog_sdk_does_not_import_app_package():
    """Dialog SDK 与 middleware 禁止反向依赖 app.*。"""
    roots = [
        AGENT_ROOT / "service_agent" / "dialog_agent",
        AGENT_ROOT / "middleware",
    ]
    violations: list[str] = []
    for root in roots:
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
                    violations.append(f"{path.relative_to(AGENT_ROOT)}:{node.lineno}")
    assert violations == []


def test_dialog_public_import_works():
    """Dialog Agent 公共入口应能在当前解释器直接导入。"""
    from medagent.agents.service_agent.dialog_agent import (
        DialogAgent,
        DialogEngine,
        DoubaoVoiceEngine,
        TextChatEngine,
    )

    assert DialogAgent.__name__ == "DialogAgent"
    assert DialogEngine.__name__ == "DialogEngine"
    assert DoubaoVoiceEngine.__name__ == "DoubaoVoiceEngine"
    assert TextChatEngine.__name__ == "TextChatEngine"


def test_dialog_public_import_works_without_pytest_path_injection():
    """安装后的 wheel 必须在隔离解释器中提供 Dialog Agent。"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "from medagent.agents.service_agent.dialog_agent "
                "import DialogAgent; print(DialogAgent.__name__)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "DialogAgent"
