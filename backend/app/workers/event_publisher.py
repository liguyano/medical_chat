"""Redis Stream事件发布器
作用：封装事件发布到Redis Stream的逻辑
"""
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.utils.redis_client import get_redis
from app.schemas.events import BaseEvent, EventType
from app.configs.app_config import get_app_config

logger = logging.getLogger(__name__)


class DialogEventPublisher:
    """对话事件发布器
    作用：发布对话事件到Redis Stream
    """

    def __init__(self, session_id: str):
        """初始化事件发布器
        Args:
            - session_id: 会话ID
        """
        self.session_id = session_id
        self.stream_key = f"dialog_stream:{session_id}"
        self.redis = get_redis()
        config = get_app_config()
        self.max_len = config.redis.stream_maxlen

    def publish(self, event: BaseEvent) -> Optional[str]:
        """发布单个事件
        作用：将事件序列化并发布到Redis Stream
        Args:
            - event: 事件对象（BaseEvent子类）
        Return:
            - message_id: Redis Stream消息ID，失败返回None
        """
        try:
            # 序列化事件为字典
            event_dict = event.model_dump(mode='json')

            # 发布到Redis Stream
            message_id = self.redis.xadd(
                stream_key=self.stream_key,
                fields=event_dict,
                max_len=self.max_len
            )

            logger.debug(
                f"事件发布成功: {event.event_type} -> {self.stream_key} (id={message_id})"
            )
            return message_id

        except Exception as e:
            logger.error(f"事件发布失败: {event.event_type} -> {e}")
            # 降级：保存到数据库message_queue表（TODO: 实现降级逻辑）
            self._fallback_to_db(event)
            return None

    def publish_batch(self, events: List[BaseEvent]) -> List[Optional[str]]:
        """批量发布事件
        作用：批量发布多个事件
        Args:
            - events: 事件列表
        Return:
            - message_ids: 消息ID列表（失败的为None）
        """
        message_ids = []
        for event in events:
            message_id = self.publish(event)
            message_ids.append(message_id)

        success_count = sum(1 for mid in message_ids if mid is not None)
        logger.info(
            f"批量发布完成: {success_count}/{len(events)} 成功"
        )
        return message_ids

    def _fallback_to_db(self, event: BaseEvent):
        """降级到数据库保存
        作用：Redis失败时将事件保存到数据库
        Args:
            - event: 事件对象
        """
        try:
            # TODO: 实现数据库降级逻辑
            # 1. 序列化事件
            # 2. 插入message_queue表
            # 3. 后台任务定期重试发布
            logger.warning(f"事件降级保存（未实现）: {event.event_type}")
        except Exception as e:
            logger.error(f"降级保存失败: {e}")


class StreamKeyHelper:
    """Stream键名辅助类
    作用：提供统一的Stream键名生成规则
    """

    @staticmethod
    def dialog_stream(session_id: str) -> str:
        """对话流键名
        Args:
            - session_id: 会话ID
        Return:
            - stream_key: dialog_stream:{session_id}
        """
        return f"dialog_stream:{session_id}"

    @staticmethod
    def schedule_stream(task_id: str) -> str:
        """调度任务流键名
        Args:
            - task_id: 任务ID
        Return:
            - stream_key: schedule_stream:{task_id}
        """
        return f"schedule_stream:{task_id}"

    @staticmethod
    def extraction_stream(session_id: str) -> str:
        """抽取结果流键名
        Args:
            - session_id: 会话ID
        Return:
            - stream_key: extraction_stream:{session_id}
        """
        return f"extraction_stream:{session_id}"
