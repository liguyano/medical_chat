"""只写连接元数据的轮转诊断日志，不记录音频、提示词或交流内容。"""

import json
import logging
import os
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER = logging.getLogger("medical.voice.diagnostics")
_ALLOWED = {
    "previous_connection_id",
    "audio_rms",
    "audio_peak",
    "session_id",
    "connection_id",
    "model",
    "phase",
    "close_code",
    "error_type",
    "elapsed_ms",
    "attempt",
    "last_event",
    "provider_code",
    "provider_type",
    "provider_event_id",
    "response_id",
    "generation_id",
    "http_status",
    "retryable",
    "received_bytes",
    "sent_bytes",
    "lifetime_ms",
    "last_event_age_ms",
}


def log_voice_event(event: str, **metadata) -> None:
    payload = {"time": datetime.now(UTC).isoformat(), "event": event}
    for key, value in metadata.items():
        if key not in _ALLOWED or value is None:
            continue
        if isinstance(value, (bool, int, float)):
            payload[key] = value
        else:
            # 只允许短标识符，未知自由文本不进入专用诊断日志。
            label = str(value)
            payload[key] = (
                label[:128] if re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", label) else "redacted"
            )
    _LOGGER.info(json.dumps(payload, ensure_ascii=False))


def setup_voice_diagnostics(path: Path | None = None) -> RotatingFileHandler | None:
    path = path or (
        Path(__file__).resolve().parents[2] / "logs" / f"voice-diagnostics-{os.getpid()}.jsonl"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
    except OSError:
        # 文件诊断不可用不能阻止 API/Worker 启动；继续输出到已有控制台。
        if not _LOGGER.handlers:
            _LOGGER.propagate = True
            _LOGGER.setLevel(logging.INFO)
        logging.getLogger(__name__).warning("语音诊断文件无法创建，保留控制台日志")
        return None
    for existing in list(_LOGGER.handlers):
        _LOGGER.removeHandler(existing)
        existing.close()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False
    return handler
