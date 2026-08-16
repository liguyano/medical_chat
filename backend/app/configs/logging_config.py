"""日志系统配置
作用：根据 AppConfig.logging 初始化全局日志（文本或 JSON 格式，可选写文件）。
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from app.configs.app_config import LoggingConfig, get_app_config


class _JsonFormatter(logging.Formatter):
    """JSON 日志格式化器
    作用：将日志记录序列化为单行 JSON，便于日志检索与聚合。
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(config: LoggingConfig | None = None) -> None:
    """初始化日志系统
    作用：配置根 logger 的级别、格式与输出目标。
    Args:
        - config: 日志配置；为空则从全局 AppConfig 读取。
    """
    config = config or get_app_config().logging

    level = getattr(logging, config.level.upper(), logging.INFO)

    if config.json_format:
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handlers: list[logging.Handler] = []

    # 控制台输出（UTF-8，兼容 Windows）
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    handlers.append(stream)

    # 可选文件输出
    if config.file:
        file_path = Path(config.file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    root = logging.getLogger()
    root.setLevel(level)
    # 清理已有 handler，避免重复输出
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)
