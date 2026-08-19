"""Redis Stream事件发布器
作用：封装事件发布到Redis Stream的逻辑
"""

import logging
from datetime import datetime

from app.configs.app_config import get_app_config
from app.schemas.events import BaseEvent
from app.utils.redis_client import RedisClient, get_redis

logger = logging.getLogger(__name__)


class DialogEventPublisher:
    """对话事件发布器
    作用：发布对话事件到Redis Stream
    """

    def __init__(
        self,
        session_id: str | None = None,
        redis_client: RedisClient | None = None,
    ):
        """初始化事件发布器
        Args:
            - session_id: 会话ID（可选）
            - redis_client: Redis客户端（可选，用于依赖注入）
        """
        self.session_id = session_id
        self.stream_key = f"dialog_stream:{session_id}" if session_id else None
        self.redis = redis_client or get_redis()
        config = get_app_config()
        self.max_len = config.redis.stream_maxlen

    def publish(self, event: BaseEvent) -> str | None:
        """发布单个事件
        作用：将事件序列化并发布到Redis Stream
        Args:
            - event: 事件对象（BaseEvent子类）
        Return:
            - message_id: Redis Stream消息ID，失败返回None
        """
        try:
            # 序列化事件为字典
            event_dict = event.model_dump(mode="json")

            # 发布到Redis Stream
            message_id = self.redis.xadd(
                stream_key=self.stream_key, fields=event_dict, max_len=self.max_len
            )

            logger.debug(f"事件发布成功: {event.event_type} -> {self.stream_key} (id={message_id})")
            return message_id

        except Exception as e:  # noqa: BLE001
            logger.error(f"事件发布失败: {event.event_type} -> {e}")
            # 降级：保存到数据库message_queue表（TODO: 实现降级逻辑）
            self._fallback_to_db(event)
            return None

    def publish_batch(self, events: list[BaseEvent]) -> list[str | None]:
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
        logger.info(f"批量发布完成: {success_count}/{len(events)} 成功")
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
        except Exception as e:  # noqa: BLE001
            logger.error(f"降级保存失败: {e}")

    def publish_extraction_result(
        self,
        session_id: str,
        task_id: int | str,
        extracted_fields: dict,
        confidence_scores: dict,
        message_id: str | None = None,
    ) -> str | None:
        """发布字段抽取结果事件
        作用：发布 ExtractionResultEvent 到 dialog_stream（供前端 SSE 消费）
        Args:
            - session_id: 会话ID
            - extracted_fields: 抽取的字段 {question_id: answer_value}
            - confidence_scores: 置信度 {question_id: confidence}
        Return:
            - message_id 或 None
        """
        from datetime import UTC

        from app.schemas.events import ExtractionResultEvent

        event = ExtractionResultEvent(
            event_type="extraction_result",
            session_id=session_id,
            task_id=task_id,
            message_id=message_id,
            extracted_fields=extracted_fields,
            confidence_scores=confidence_scores,
            timestamp=datetime.now(UTC),
        )

        try:
            event_dict = event.model_dump(mode="json")
            message_id = self.redis.xadd(
                stream_key=self.stream_key, fields=event_dict, max_len=self.max_len
            )

            logger.debug(
                f"[EventPublisher] 发布抽取结果: session={session_id}, "
                f"fields={len(extracted_fields)}, message_id={message_id}"
            )
            return message_id

        except Exception as e:  # noqa: BLE001
            logger.error(f"[EventPublisher] 发布抽取结果失败: {e}")
            return None


class NurseEventPublisher(DialogEventPublisher):
    """责任护士全局提醒事件发布器
    作用：把人工介入事件写入 nurse_stream:{staff_id}，供医护端全局 SSE 订阅。
    """

    def __init__(
        self,
        staff_id: int | str,
        redis_client: RedisClient | None = None,
    ) -> None:
        super().__init__(session_id=None, redis_client=redis_client)
        self.staff_id = str(staff_id)
        self.stream_key = f"nurse_stream:{self.staff_id}"


class StreamKeyHelper:
    """Stream键名辅助类
    作用:提供统一的Stream键名生成规则
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
