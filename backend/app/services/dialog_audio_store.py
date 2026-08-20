"""对话音频持久化。

作用：将实时语音输入和模型输出保存为可回放的 PCM 文件，Redis Stream
只保存音频索引，避免把大体积 Base64 音频写入事件流。
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

_SAFE_PART = re.compile(r"[^A-Za-z0-9_.-]+")


class DialogAudioStore:
    """本地对话音频存储。

    生产环境可以将本类替换为 OSS/对象存储实现；对外仍返回稳定的
    `/api/dialog/{session}/audio/{filename}` 访问路径。
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "storage" / "dialog-audio"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(value: str) -> str:
        safe = _SAFE_PART.sub("_", str(value)).replace("..", "_")
        return safe[:160] or "audio"

    def save(
        self,
        *,
        session_no: str,
        generation_id: str,
        filename: str,
        data: bytes,
    ) -> str:
        """保存一段音频并返回 API 相对地址。"""
        session_part = self._safe(session_no)
        generation_part = self._safe(generation_id)
        filename_part = self._safe(filename)
        directory = self.root / session_part / generation_part
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename_part
        path.write_bytes(data)
        return (
            f"/api/dialog/{session_part}/audio/"
            f"{generation_part}/{filename_part}"
        )

    def save_wav(
        self,
        *,
        session_no: str,
        generation_id: str,
        filename: str,
        data: bytes,
        sample_rate: int,
        channels: int = 1,
    ) -> str:
        """以标准 WAV 容器保存 PCM16，返回可被浏览器直接播放的地址。"""
        if sample_rate <= 0 or channels <= 0:
            raise ValueError("音频采样率和声道数必须为正数")
        if len(data) % 2:
            data = data[:-1]
        byte_rate = sample_rate * channels * 2
        block_align = channels * 2
        header = b"".join(
            (
                b"RIFF",
                struct.pack("<I", 36 + len(data)),
                b"WAVEfmt ",
                struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, 16),
                b"data",
                struct.pack("<I", len(data)),
            )
        )
        return self.save(
            session_no=session_no,
            generation_id=generation_id,
            filename=filename,
            data=header + data,
        )

    def resolve(
        self,
        *,
        session_no: str,
        generation_id: str,
        filename: str,
    ) -> Path:
        """解析音频文件并防止路径穿越。"""
        session_part = self._safe(session_no)
        generation_part = self._safe(generation_id)
        filename_part = self._safe(filename)
        root = (self.root / session_part / generation_part).resolve()
        path = (root / filename_part).resolve()
        if root not in path.parents:
            raise ValueError("非法音频路径")
        return path
