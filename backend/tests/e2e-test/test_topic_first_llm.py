"""可选真实模型合成场景，不访问患者数据库或语音设备。"""

import os
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from medagent.agents.service_agent.dialog_agent.prompt import (
    build_system_prompt,
    build_topic_turn_instruction,
)
from medagent.agents.service_agent.dialog_agent.topic_planner import plan_topic_turn
from medagent.agents.service_agent.schedule_agent import QuestionTask
from medagent.providers import create_chat_model

from app.configs.app_config import get_app_config
from app.services.voice_gateway import VOICE_TOOLS, VoiceGateway


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


@pytest.mark.asyncio
@pytest.mark.real_llm
@pytest.mark.parametrize("voice", [False, True])
async def test_continuous_topics_across_six_turns(voice):
    """语音组只模拟指令的文本表现，不代表真实音频或数据抽取端到端测试。"""
    if os.getenv("RUN_TOPIC_LLM") != "1":
        pytest.skip("设置 RUN_TOPIC_LLM=1 才调用真实模型")
    model = create_chat_model(get_app_config().get_agent_model_config("dialog_agent"))
    tasks = [
        QuestionTask(
            question_id=i,
            question_code=f"q{i}",
            question_name=name,
            patient_text=reference,
            question_type="文本",
            required=True,
            sort_no=i,
        )
        for i, name, reference in [
            (1, "行走协助", "走路是否需要搀扶"),
            (2, "进食协助", "吃饭是否需要帮助"),
            (3, "起身移动", "坐下后能否自行起身"),
            (4, "睡眠", "最近入睡和夜间醒来情况"),
        ]
    ]
    system = (
        VoiceGateway._build_remaining_assessment_instructions({}, tasks)
        if voice
        else build_system_prompt({}, tasks)
    )
    history = [{"role": "assistant", "content": "咱们先聊聊您平时喜欢做什么。"}]
    scripts = [
        ("我喜欢散步，自己在附近转几圈，不用人扶，回来坐一会儿。", {1}),
        ("听得到我说话吗？", set()),
        ("听到就好。我坐下歇歇后，自己起来也不用人扶。", {3}),
        ("平时还喜欢自己煮面条吃。", set()),
        ("面条我自己拿筷子吃，不用别人帮忙。", {2}),
        ("晚上看会儿电视就睡觉，不过夜里经常醒。", set()),
    ]
    completed = set()
    for n, (user, new_answers) in enumerate(scripts):
        completed |= new_answers
        remaining = [t for t in tasks if t.question_id not in completed]
        history.append({"role": "user", "content": user})
        instruction = ""
        if not voice:
            plan = await plan_topic_turn(model, remaining, history, user)
            if n == 0:
                assert plan.question_id == 3, "应从散步回来休息衔接起身，不按列表先问进食"
            instruction = plan.instructions() + "这是持续中的交流，不重新开场。"
        messages = [SystemMessage(content=system)]
        if instruction:
            messages.append(SystemMessage(content=instruction))
        messages.extend(
            HumanMessage(content=h["content"])
            if h["role"] == "user"
            else AIMessage(content=h["content"])
            for h in history
        )
        answer = str((await model.ainvoke(messages)).content)
        print(f"\n{'语音提示模拟' if voice else '文字'}第{n + 1}轮：{answer}", flush=True)
        assert not any(
            word in answer
            for word in (
                "评估表",
                "选项",
                "来分类",
                "身体很硬朗",
                "我是AI护理助手",
                "可以开始吗",
                "10-15分钟",
            )
        )
        assert not re.search(r"接下来.{0,12}(评估|移动情况)", answer)
        if n == 1:
            assert "听" in answer and not any(mark in answer for mark in ("？", "?"))
        if n > 2:
            assert not any(word in answer for word in ("走多远", "经常步行", "起身需要"))
        history.append({"role": "assistant", "content": answer})


@pytest.mark.asyncio
@pytest.mark.real_llm
@pytest.mark.parametrize("voice", [False, True])
async def test_game_topic_is_brief_and_asks_one_question_per_turn(voice):
    if os.getenv("RUN_TOPIC_LLM") != "1":
        pytest.skip("设置 RUN_TOPIC_LLM=1 才调用真实模型")
    model = create_chat_model(get_app_config().get_agent_model_config("dialog_agent"))
    generation_model = model.bind_tools(VOICE_TOOLS) if voice else model
    question = QuestionTask(
        question_id=1,
        question_code="vision",
        question_name="视力",
        patient_text="看近处屏幕上的字是否清楚",
        question_type="文本",
        required=True,
        sort_no=1,
    )
    system = (
        VoiceGateway._build_remaining_assessment_instructions({}, [question])
        if voice
        else build_system_prompt({}, [question])
    )
    history = [AIMessage(content="您平时喜欢做什么？")]
    for n, user in enumerate(["喜欢打游戏。", "手机上玩斗地主。", "屏幕上的字看得清楚。"]):
        history.append(HumanMessage(content=user))
        messages = [SystemMessage(content=system)]
        if not voice:
            messages.append(
                SystemMessage(content=build_topic_turn_instruction(question, introduce=n == 0))
            )
        messages.extend(history)
        response = await generation_model.ainvoke(messages)
        answer = str(response.content)
        if response.tool_calls:
            assert voice and n == 2
            assert all(call["name"] == "request_assessment_finish" for call in response.tool_calls)
            assert not answer.strip()
            print("\n语音提示模拟：原生结束检查工具调用，无患者可见旁白", flush=True)
            continue
        print(f"\n{'语音提示模拟' if voice else '文字'}游戏第{n + 1}轮：{answer}", flush=True)
        assert len(answer) <= 60, "普通回复超过60字符"
        assert answer.count("？") + answer.count("?") <= 1
        if n == 1:
            assert not ("清楚" in answer and any(x in answer for x in ["放大", "眼镜", "累"]))
        assert not any(
            x in answer for x in ["患者回答后", "下一个评估话题", "（", "(", "另外", "心态很年轻"]
        )
        history.append(AIMessage(content=answer))
