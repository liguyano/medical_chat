"""可选真实模型合成场景，不访问患者数据库或语音设备。"""

import os

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from medagent.agents.service_agent.dialog_agent.prompt import (
    build_system_prompt,
    build_topic_turn_instruction,
)
from medagent.agents.service_agent.schedule_agent import QuestionTask
from medagent.providers import create_chat_model

from app.configs.app_config import get_app_config
from app.services.voice_gateway import VoiceGateway


@pytest.mark.asyncio
@pytest.mark.real_llm
@pytest.mark.parametrize("voice", [False, True])
async def test_real_model_starts_with_topic_before_sensation_details(voice):
    if os.getenv("RUN_TOPIC_LLM") != "1":
        pytest.skip("设置 RUN_TOPIC_LLM=1 才调用配置中的真实文本模型")
    model = create_chat_model(get_app_config().get_agent_model_config("dialog_agent"))
    question = QuestionTask(
        question_id=1,
        question_code="sensation",
        question_name="感觉",
        patient_text="有没有发麻，或冷热、疼痛感觉改变？",
        question_type="文本",
        required=True,
        sort_no=1,
    )
    system = (
        VoiceGateway._build_remaining_assessment_instructions({}, [question])
        if voice
        else build_system_prompt({}, [question])
    )
    messages = [SystemMessage(content=system)]
    if not voice:
        messages.append(
            SystemMessage(content=build_topic_turn_instruction(question, introduce=True))
        )
    messages.append(HumanMessage(content="可以开始了。"))
    first = await model.ainvoke(messages)
    text = str(first.content)
    print(f"\n{'语音指令文本模拟' if voice else '文字'}引入：{text}")
    assert any(word in text for word in ("喜欢", "爱", "平时", "日常"))
    assert not any(word in text for word in ("发麻", "麻木", "冷热", "疼痛", "感觉异常"))
    messages.extend([AIMessage(content=text), HumanMessage(content="我平时爱做饭，喜欢煮面条。")])
    if not voice:
        messages.append(
            SystemMessage(content=build_topic_turn_instruction(question, introduce=False))
        )
    second = await model.ainvoke(messages)
    print(f"展开：{second.content}")
    assert str(second.content).strip()
