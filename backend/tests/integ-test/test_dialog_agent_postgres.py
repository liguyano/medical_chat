"""Dialog Agent 核心编排与真实 PostgreSQL 对话历史集成测试。"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from medagent.agents.service_agent.dialog_agent import DialogAgent, DialogEngine
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.managers.dialog_history_manager import DialogHistoryManager
from app.models import CareTask, InteractionSession, Patient, PatientEncounter


class DeterministicTextEngine(DialogEngine):
    """仅隔离外部模型协议，保留 Dialog Agent 与真实数据库协作。"""

    def __init__(self) -> None:
        self.input_text = ""
        self.closed = False

    async def create_session(
        self,
        system_prompt: str,
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        assert "CICARE" in system_prompt
        assert tools

    async def send_input(self, input_data: Any) -> None:
        self.input_text = str(input_data)

    async def stream_response(self) -> AsyncGenerator[dict[str, Any], None]:
        yield {"type": "text", "content": "已记录："}
        yield {"type": "text", "content": self.input_text}
        yield {"type": "response_done"}

    async def send_tool_result(self, call_id: str, result: Any) -> bool:
        return False

    async def update_session(
        self,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        return None

    async def close_session(self) -> None:
        self.closed = True


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _seed_interaction_session(session_factory) -> str:
    """在测试事务中创建最小患者—住院—任务—对话链路。"""
    now = datetime.now(UTC)
    with session_factory() as db:
        patient = Patient(
            patient_no=_uid("DIALOG-PAT"),
            patient_name="Dialog集成测试患者",
            sex="未知",
            creator="pytest",
            updator="pytest",
        )
        db.add(patient)
        db.flush()
        encounter = PatientEncounter(
            encounter_no=_uid("DIALOG-ENC"),
            patient_id=patient.id,
            inpatient_no=_uid("DIALOG-INP"),
            admission_time=now,
            encounter_status="在院",
            creator="pytest",
            updator="pytest",
        )
        db.add(encounter)
        db.flush()
        task = CareTask(
            task_no=_uid("DIALOG-TASK"),
            patient_id=patient.id,
            encounter_id=encounter.id,
            task_type="入院评估",
            task_name="Dialog Agent 集成测试",
            task_source="pytest",
            collection_mode="ai_dialogue",
            task_status="进行中",
            creator="pytest",
            updator="pytest",
        )
        db.add(task)
        db.flush()
        interaction = InteractionSession(
            session_no=_uid("DIALOG-SESSION"),
            task_id=task.id,
            patient_id=patient.id,
            encounter_id=encounter.id,
            participant_type="患者本人",
            interaction_type="评估",
            channel_type="文字",
            session_status="进行中",
            started_at=now,
            creator="pytest",
            updator="pytest",
        )
        db.add(interaction)
        db.commit()
        return interaction.session_no


@pytest.mark.asyncio
async def test_dialog_agent_persists_patient_and_ai_messages(postgres_session_factory):
    """完整一轮文本编排应把患者原话和 AI 回答写入真实 PostgreSQL。"""
    session_no = _seed_interaction_session(postgres_session_factory)
    history = DialogHistoryManager(postgres_session_factory)
    engine = DeterministicTextEngine()
    agent = DialogAgent(
        session_id=f"runtime-{uuid4().hex}",
        patient_info={"name": "测试患者"},
        task_list=[
            QuestionTask(
                question_id=1,
                question_code="smoking",
                question_name="吸烟史",
                patient_text="您是否吸烟？",
                question_type="单选",
                required=True,
                sort_no=1,
            )
        ],
        engine=engine,
        history_store=history,
    )

    await agent.initialize()
    answer = await agent.handle_patient_input("我不吸烟。", session_no=session_no)
    messages = await history.get_dialog_history(session_no)
    await agent.close()

    assert answer == "已记录：我不吸烟。"
    assert [(message.role_type, message.content_text) for message in messages] == [
        ("患者", "我不吸烟。"),
        ("AI", "已记录：我不吸烟。"),
    ]
    assert {message.turn_no for message in messages} == {1}
    assert engine.closed is True
