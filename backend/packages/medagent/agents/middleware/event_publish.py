"""事件发布中间件
作用：after_agent 统一发布 DialogTurnEvent / ToolCallEvent 到 Redis Stream。
"""
import logging
from typing import Any, Dict, List, Optional

from app.managers.event_publisher import DialogEventPublisher
from app.schemas.events import DialogTurnEvent, ToolCallEvent

from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class EventPublishMiddleware(DialogMiddleware):
    """事件发布中间件
    作用：对话轮次结束后，发布事件到 Redis Stream 供其他智能体消费。
    """

    def __init__(self, session_id: str):
        """初始化事件发布中间件
        Args:
            - session_id: 会话 ID
        """
        self.session_id = session_id
        self.publisher = DialogEventPublisher(session_id)
        logger.info(f"[EventPublishMiddleware] 初始化: session_id={session_id}")

    async def before_agent(self, context: Dict[str, Any]) -> None:
        """执行前钩子：事件发布在 after 阶段进行
        Args:
            - context: 上下文字典
        """
        pass

    async def after_agent(self, context: Dict[str, Any], output: Any) -> None:
        """执行后钩子：发布对话轮次事件
        Args:
            - context: 上下文字典，包含 turn_number、patient_input、tool_calls 等
            - output: 智能体输出（AI 回复文本）
        """
        try:
            # 1. 发布 DialogTurnEvent
            turn_number = context.get("turn_number", 0)
            patient_input = context.get("patient_input", "")
            tool_calls = context.get("tool_calls", [])

            turn_event = DialogTurnEvent(
                session_id=self.session_id,
                turn_number=turn_number,
                question=patient_input,
                answer=str(output) if output else "",
                tool_calls=tool_calls if tool_calls else None,
            )
            event_id = self.publisher.publish(turn_event)
            if event_id:
                logger.info(
                    f"[EventPublishMiddleware] 发布 DialogTurnEvent: "
                    f"turn={turn_number}, event_id={event_id}"
                )

            # 2. 发布 ToolCallEvent（如有工具调用）
            if tool_calls:
                for tool_call in tool_calls:
                    tool_event = ToolCallEvent(
                        session_id=self.session_id,
                        turn_number=turn_number,
                        tool_name=tool_call.get("name", ""),
                        tool_args=tool_call.get("arguments", {}),
                        tool_result=tool_call.get("result"),
                    )
                    tool_event_id = self.publisher.publish(tool_event)
                    if tool_event_id:
                        logger.info(
                            f"[EventPublishMiddleware] 发布 ToolCallEvent: "
                            f"tool={tool_call.get('name')}, event_id={tool_event_id}"
                        )

        except Exception as e:
            logger.error(f"[EventPublishMiddleware] 事件发布失败: {e}", exc_info=True)
