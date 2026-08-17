"""Dialog Agent 真实 OpenAI 兼容文本模型端到端测试。"""

import os

import pytest
from medagent.agents.service_agent.dialog_agent import DialogAgent, TextChatEngine
from medagent.agents.service_agent.dialog_agent.agent import GENERIC_ERROR_MESSAGE
from medagent.agents.service_agent.schedule_agent import QuestionTask


@pytest.mark.asyncio
@pytest.mark.real_llm
async def test_dialog_agent_completes_real_text_model_turn():
    """真实千问模型应完成初始化、患者输入和流式中文回答链路。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        pytest.skip("未配置 DASHSCOPE_API_KEY，无法执行真实文本模型测试")

    engine = TextChatEngine(
        api_key=api_key,
        model=os.getenv("DIALOG_TEST_MODEL", "qwen-plus"),
        api_base=os.getenv(
            "DIALOG_TEST_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        timeout=60.0,
    )
    agent = DialogAgent(
        session_id="dialog-real-text-e2e",
        patient_info={"name": "张三", "age": 65},
        task_list=[
            QuestionTask(
                question_id=1,
                question_code="smoking",
                question_name="吸烟史",
                patient_text="您是否吸烟？",
                question_type="单选",
                required=True,
                sort_no=1,
            ),
            QuestionTask(
                question_id=2,
                question_code="allergy",
                question_name="药物过敏史",
                patient_text="您是否有药物过敏？",
                question_type="文本",
                required=True,
                sort_no=2,
            ),
        ],
        engine=engine,
    )

    try:
        await agent.initialize()
        answer = await agent.handle_patient_input(
            "您好，我叫张三，今年65岁，我不吸烟，请继续为我做入院评估。"
        )
    finally:
        await agent.close()

    assert answer.strip()
    assert answer != GENERIC_ERROR_MESSAGE
    assert "文本模型调用失败" not in answer


@pytest.mark.asyncio
@pytest.mark.real_llm
async def test_dialog_agent_completes_real_tool_call_round_trip():
    """真实模型工具调用、占位工具执行、结果回传和患者回复应形成闭环。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        pytest.skip("未配置 DASHSCOPE_API_KEY，无法执行真实文本模型测试")

    engine = TextChatEngine(
        api_key=api_key,
        model=os.getenv("DIALOG_TEST_MODEL", "qwen-plus"),
        api_base=os.getenv(
            "DIALOG_TEST_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        timeout=60.0,
    )
    agent = DialogAgent(
        session_id="dialog-real-tool-e2e",
        patient_info={"name": "张三", "age": 65},
        task_list=[
            QuestionTask(
                question_id=1,
                question_code="surgery",
                question_name="手术安排",
                patient_text="您近期是否安排了手术？",
                question_type="文本",
                required=True,
                sort_no=1,
            )
        ],
        engine=engine,
    )

    try:
        await agent.initialize()
        answer = await agent.handle_patient_input(
            "护士说我明天要做手术，请现在为我准备手术知情同意书。"
        )
        tool_messages = [
            message for message in engine.messages if message.get("role") == "tool"
        ]
    finally:
        await agent.close()

    assert tool_messages
    assert answer.strip()
    assert answer != GENERIC_ERROR_MESSAGE
