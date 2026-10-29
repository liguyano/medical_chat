"""真实语音模型+合成PCM多轮验证，禁止使用患者录音或麦克风。"""

import asyncio
import base64
import json
import os
import wave
from pathlib import Path

import pytest
from medagent.agents.service_agent.schedule_agent import QuestionTask, ScheduleTaskTodo
from medagent.configs.model_config import ModelType

from app.configs.app_config import get_app_config
from app.services.qwen_realtime_client import QwenRealtimeClient
from app.services.voice_gateway import VOICE_TOOLS, VoiceGateway
from app.services.voice_provisional import VoiceProvisionalState


@pytest.mark.asyncio
@pytest.mark.real_llm
async def test_actual_realtime_topics_with_synthetic_pcm():
    if os.getenv("RUN_ACTUAL_VOICE") != "1":
        pytest.skip("需显式授权并设置RUN_ACTUAL_VOICE=1和合成音频目录")
    directory = Path(os.environ["SYNTHETIC_VOICE_DIR"])
    config = get_app_config().get_agent_model_config("dialog_agent", ModelType.VOICE)
    client = QwenRealtimeClient(
        api_key=config.resolved_api_key(),
        model=config.model,
        websocket_url=config.websocket_url,
        voice=config.voice or "longanqian",
        timeout=30,
    )
    tasks = [
        QuestionTask(
            question_id=i,
            question_code=code,
            question_name=name,
            patient_text=ref,
            question_type="文本",
            required=True,
            sort_no=i,
        )
        for i, code, name, ref in [
            (1, "vision", "视力", "看近处屏幕上的字是否清楚"),
            (2, "eating", "进食", "吃饭是否需要帮助"),
            (3, "sleep", "睡眠", "最近入睡和夜间醒来情况"),
        ]
    ]
    queue = asyncio.Queue()
    route = []
    if os.getenv("TOPIC_ROUTE_PLAN_FILE"):
        prepared = ScheduleTaskTodo.model_validate_json(
            Path(os.environ["TOPIC_ROUTE_PLAN_FILE"]).read_text(encoding="utf-8")
        )
        tasks = prepared.tasks
        route = prepared.topic_route

    async def collect():
        try:
            async for event in client.events():
                await queue.put(event)
        except (OSError, RuntimeError, ValueError) as exc:
            await queue.put({"type": "collector_error", "message": str(exc)})

    reader = None
    replies = []
    provisional = VoiceProvisionalState()
    try:
        await client.connect(
            instructions=VoiceGateway._build_remaining_assessment_instructions(
                {}, tasks, topic_route=route
            ),
            tools=VOICE_TOOLS,
            turn_detection="server_vad",
        )
        reader = asyncio.create_task(collect())
        for n in range(6):
            with wave.open(str(directory / f"{n}.wav"), "rb") as wav:
                assert (
                    wav.getframerate() == 16000
                    and wav.getnchannels() == 1
                    and wav.getsampwidth() == 2
                )
                pcm = wav.readframes(wav.getnframes())

            async def feed(pcm=pcm):
                data = pcm + b"\0" * 48000
                for start in range(0, len(data), 3200):
                    await client.append_audio(data[start : start + 3200])
                    await asyncio.sleep(0.1)

            sender = asyncio.create_task(feed())
            audio_text = []
            text = []
            asr = ""
            audio_bytes = 0
            speech_started = False
            active_response = None
            pending_calls = []
            tool_rounds = 0
            try:
                async with asyncio.timeout(60):
                    while True:
                        event = await queue.get()
                        typ = event.get("type", "")
                        if typ in {"error", "collector_error"}:
                            raise AssertionError(str(event.get("error") or event.get("message")))
                        if typ == "input_audio_buffer.speech_started":
                            speech_started = True
                        if typ == "response.created" and speech_started:
                            active_response = event.get("response", {}).get("id")
                        if typ.endswith("input_audio_transcription.completed"):
                            asr = event.get("transcript", "")
                            provisional.begin_turn(f"synthetic-{n}", asr)
                        response_id = event.get("response_id") or event.get("response", {}).get(
                            "id"
                        )
                        if response_id and response_id != active_response:
                            continue
                        if typ == "response.function_call_arguments.done":
                            pending_calls.append(event)
                        if typ == "response.audio_transcript.delta":
                            audio_text.append(event.get("delta", ""))
                        elif typ == "response.text.delta":
                            text.append(event.get("delta", ""))
                        if typ == "response.audio.delta":
                            audio_bytes += len(base64.b64decode(event.get("delta", "")))
                        if typ == "response.done" and active_response:
                            if event.get("response", {}).get("status") == "cancelled":
                                active_response = None
                                continue
                            if pending_calls:
                                tool_rounds += 1
                                assert tool_rounds <= 3, "语音模型反复调用结束检查"
                                if not asr:
                                    try:
                                        async with asyncio.timeout(3):
                                            while not asr:
                                                extra = await queue.get()
                                                if extra.get("type", "").endswith(
                                                    "input_audio_transcription.completed"
                                                ):
                                                    asr = extra.get("transcript", "")
                                                    provisional.begin_turn(f"synthetic-{n}", asr)
                                    except TimeoutError:
                                        pass
                                known = {"vision"} if n >= 1 else set()
                                if n >= 4:
                                    known.add("eating")
                                remaining = [q for q in tasks if q.question_code not in known]
                                remaining_ids = {q.question_id for q in remaining}
                                provisional.settle(remaining_ids, set())
                                for call in pending_calls:
                                    if call["name"] == "mark_patient_response_heard":
                                        args = json.loads(call.get("arguments") or "{}")
                                        try:
                                            provisional.mark(
                                                args.get("question_ids", []),
                                                args.get("quote", ""),
                                                {q.question_id for q in tasks},
                                            )
                                            result = {
                                                "success": True,
                                                "formal_answer": False,
                                                "message": "仅暂放待后台核实，先接话或聊其他相关内容，不重复问题",
                                            }
                                        except ValueError as exc:
                                            print(
                                                "合成初判被拒绝",
                                                str(exc),
                                                "args=",
                                                args,
                                                "asr=",
                                                asr,
                                                flush=True,
                                            )
                                            result = {
                                                "success": False,
                                                "message": "初判必须引用当前真实测试原话",
                                            }
                                    else:
                                        assert call["name"] == "request_assessment_finish"
                                        result = {
                                            "completed": False,
                                            "remaining_question_ids": list(remaining_ids),
                                            "message": "模拟后台仍有缺项，不得结束",
                                        }
                                    print(
                                        "\n合成语音工具",
                                        call["name"],
                                        "success=",
                                        result.get("success"),
                                        flush=True,
                                    )
                                    await client.send_tool_result(call["call_id"], result)
                                available = provisional.available(remaining_ids)
                                await client.update_instructions(
                                    VoiceGateway._build_remaining_assessment_instructions(
                                        {},
                                        [q for q in remaining if q.question_id in available],
                                        topic_route=route,
                                    )
                                    + "仅有暂放事项时简短回应等待后台，不宣布完成。"
                                )
                                pending_calls = []
                                active_response = None
                                await client.create_response()
                                continue
                            if audio_text or text:
                                break
                            active_response = None
            finally:
                await sender
            reply = "".join(audio_text or text)
            print(
                f"\n真实语音第{n + 1}轮 ASR={asr} 回复={reply} 音频字节={audio_bytes}", flush=True
            )
            replies.append(reply)
            assert reply and audio_bytes > 0
        assert all(replies), "每个合成语音轮次都必须有真实回复"
        assert [tool["function"]["name"] for tool in VOICE_TOOLS] == ["request_assessment_finish"]
    finally:
        if reader:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        await client.close()
