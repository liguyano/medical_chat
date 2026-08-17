"""超时控制中间件
作用：调用 SessionTimeoutManager.update_activity，检测无响应超时。
"""
import logging
from typing import Any, Dict

from app.managers.session_timeout_manager import SessionTimeoutManager

from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class TimeoutMiddleware(DialogMiddleware):
    """超时控制中间件
    作用：每轮对话更新活动时间戳，配合 TimeoutMonitor 检测患者无响应超时。
    """

    def __init__(self, timeout_minutes: int = 5):
        """初始化超时控制中间件
        Args:
            - timeout_minutes: 超时阈值（默认 5 分钟）
        """
        self.timeout_manager = SessionTimeoutManager(timeout_minutes=timeout_minutes)
        logger.info(f"[TimeoutMiddleware] 初始化: 超时阈值={timeout_minutes}分钟")

    async def before_agent(self, context: Dict[str, Any]) -> None:
        """执行前钩子：更新会话活动时间戳
        Args:
            - context: 上下文字典，包含 session_id
        """
        session_id = context.get("session_id")
        if not session_id:
            return

        try:
            # 更新 Redis 中的活动时间戳
            self.timeout_manager.update_activity(session_id)
            logger.debug(f"[TimeoutMiddleware] 更新活动时间戳: session_id={session_id}")
        except Exception as e:
            logger.error(f"[TimeoutMiddleware] 更新活动时间戳失败: {e}", exc_info=True)

    async def after_agent(self, context: Dict[str, Any], output: Any) -> None:
        """执行后钩子：再次更新活动时间戳（AI 响应完成后）
        Args:
            - context: 上下文字典
            - output: 智能体输出
        """
        session_id = context.get("session_id")
        if not session_id:
            return

        try:
            # AI 响应完成后再次更新时间戳
            self.timeout_manager.update_activity(session_id)
            logger.debug(f"[TimeoutMiddleware] AI 响应后更新活动时间戳: session_id={session_id}")
        except Exception as e:
            logger.error(f"[TimeoutMiddleware] 更新活动时间戳失败: {e}", exc_info=True)
