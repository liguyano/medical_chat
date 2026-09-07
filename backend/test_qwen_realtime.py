"""独立验证阿里云百炼 Qwen-Audio Realtime WebSocket 鉴权与会话初始化。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import websockets
from websockets.exceptions import InvalidStatus


WORKSPACE_ID = "ws-lq4znjybupgtwwds"
MODEL = "qwen-audio-3.0-realtime-flash"
WEBSOCKET_URL = (
    f"wss://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com"
    f"/api-ws/v1/realtime?model={MODEL}"
)


def _pretty_event(raw_event: str | bytes) -> str:
    """尽量格式化服务端 JSON；非 JSON 内容按原文返回。"""
    if isinstance(raw_event, bytes):
        raw_event = raw_event.decode("utf-8", errors="replace")
    try:
        payload: Any = json.loads(raw_event)
    except json.JSONDecodeError:
        return raw_event
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def verify_realtime_connection() -> int:
    """建立连接并发送最小 session.update，返回进程退出码。"""
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 DASHSCOPE_API_KEY。", file=sys.stderr)
        return 2

    try:
        async with websockets.connect(
            WEBSOCKET_URL,
            additional_headers={
                "Authorization": f"Bearer {api_key}",
                "X-DashScope-WorkSpace": WORKSPACE_ID,
                "x-dashscope-dataInspection": "disable",
            },
            open_timeout=15,
            ping_interval=20,
            ping_timeout=10,
        ) as websocket:
            print("WebSocket 握手成功。")

            first_event = await asyncio.wait_for(websocket.recv(), timeout=10)
            print("服务端首个事件：")
            print(_pretty_event(first_event))

            await websocket.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "modalities": ["text", "audio"],
                            "voice": "longanqian",
                            "input_audio_format": "pcm",
                            "output_audio_format": "pcm",
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.1,
                                "silence_duration_ms": 900,
                            },
                        },
                    },
                    ensure_ascii=False,
                )
            )

            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            print("session.update 响应：")
            print(_pretty_event(response))
            return 0

    except InvalidStatus as exc:
        response = exc.response
        print(f"WebSocket 握手失败：HTTP {response.status_code}", file=sys.stderr)
        body = bytes(response.body or b"").decode("utf-8", errors="replace")
        if body:
            print(f"响应内容：{body}", file=sys.stderr)
        request_id = response.headers.get("x-request-id")
        if request_id:
            print(f"Request ID：{request_id}", file=sys.stderr)
        return 1
    except Exception as exc:  # 独立诊断脚本需要展示供应商或网络异常类型
        print(f"连接异常：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify_realtime_connection()))
