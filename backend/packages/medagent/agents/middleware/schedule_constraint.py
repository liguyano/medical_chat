"""调度约束中间件
作用：读取 Redis 中 Schedule Agent 发布的约束，注入 system_prompt。
"""
import json
import logging
from typing import Any, Dict, Optional

from app.utils.redis_client import RedisClient

from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class ScheduleConstraintMiddleware(DialogMiddleware):
    """调度约束中间件
    作用：从 Redis Stream 读取 Schedule Agent 发布的 ConstraintEvent，注入约束提示。
    """

    def __init__(self, redis_client: Optional[RedisClient] = None):
        """初始化调度约束中间件
        Args:
            - redis_client: Redis 客户端（用于读取 constraint_stream）
        """
        self.redis_client = redis_client or RedisClient()
        logger.info("[ScheduleConstraintMiddleware] 初始化完成")

    async def before_agent(self, context: Dict[str, Any]) -> None:
        """执行前钩子：读取调度约束并注入
        Args:
            - context: 上下文字典，包含 session_id、constraints 等
        """
        session_id = context.get("session_id")
        if not session_id:
            return

        # 从 Redis 读取最近的约束事件
        # Stream key: constraint_stream:{session_id}
        stream_key = f"constraint_stream:{session_id}"
        try:
            # 读取最近 1 条消息（XREVRANGE，倒序）
            messages = self.redis_client.client.xrevrange(stream_key, count=1)
            if not messages:
                return

            # 解析约束事件
            msg_id, msg_data = messages[0]
            event_data = msg_data.get(b"data")
            if not event_data:
                return

            event = json.loads(event_data)
            constraint_prompt = event.get("constraint_prompt", "")
            if constraint_prompt:
                logger.info(
                    f"[ScheduleConstraintMiddleware] 读取到调度约束: {constraint_prompt[:50]}..."
                )
                # 追加到 context.constraints
                if "constraints" not in context:
                    context["constraints"] = []
                context["constraints"].append(constraint_prompt)

        except Exception as e:
            logger.error(f"[ScheduleConstraintMiddleware] 读取约束失败: {e}", exc_info=True)

    async def after_agent(self, context: Dict[str, Any], output: Any) -> None:
        """执行后钩子：调度约束无需 after 处理
        Args:
            - context: 上下文字典
            - output: 智能体输出
        """
        pass
