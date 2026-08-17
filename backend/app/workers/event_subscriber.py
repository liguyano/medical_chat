"""Redis Stream事件订阅器
作用：封装事件订阅和处理逻辑
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.utils.redis_client import get_redis
from app.schemas.events import BaseEvent, EventType, EVENT_TYPE_MAP

logger = logging.getLogger(__name__)


class EventSubscriber(ABC):
    """事件订阅器基类
    作用：定义事件订阅和处理的抽象接口
    """

    def __init__(self, consumer_group: str, consumer_name: str):
        """初始化订阅器
        Args:
            - consumer_group: 消费者组名称
            - consumer_name: 消费者名称
        """
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.redis = get_redis()
        self.running = False

    @abstractmethod
    def get_stream_keys(self) -> List[str]:
        """获取需要订阅的Stream键名列表
        作用：子类实现具体的Stream键名逻辑
        Return:
            - stream_keys: Stream键名列表
        """
        pass

    @abstractmethod
    async def process_event(self, event: BaseEvent):
        """处理事件
        作用：子类实现具体的事件处理逻辑
        Args:
            - event: 事件对象
        """
        pass

    def start(self, block_ms: int = 5000, count: int = 10):
        """启动订阅器
        作用：开始订阅并处理事件
        Args:
            - block_ms: 阻塞等待时间（毫秒）
            - count: 每次读取消息数量
        """
        self.running = True
        logger.info(f"订阅器启动: group={self.consumer_group}, name={self.consumer_name}")

        try:
            # 创建消费者组（如果不存在）
            stream_keys = self.get_stream_keys()
            for stream_key in stream_keys:
                self.redis.xgroup_create(
                    stream_key=stream_key,
                    group_name=self.consumer_group,
                    id='0',
                    mkstream=True
                )

            # 主循环：订阅并处理消息
            while self.running:
                streams = {key: '>' for key in self.get_stream_keys()}
                messages = self.redis.xreadgroup(
                    group_name=self.consumer_group,
                    consumer_name=self.consumer_name,
                    streams=streams,
                    count=count,
                    block=block_ms,
                )

                # 处理接收到的消息
                for stream_key_bytes, message_list in messages:
                    stream_key = stream_key_bytes.decode('utf-8')
                    for message_id_bytes, fields_bytes in message_list:
                        message_id = message_id_bytes.decode('utf-8')
                        self._process_message(stream_key, message_id, fields_bytes)

        except KeyboardInterrupt:
            logger.info("订阅器被用户中断")
        except Exception as e:
            logger.error(f"订阅器异常: {e}")
        finally:
            self.stop()

    def stop(self):
        """停止订阅器"""
        self.running = False
        logger.info(f"订阅器已停止: {self.consumer_name}")

    def _process_message(self, stream_key: str, message_id: str, fields_bytes: Dict[bytes, bytes]):
        """处理单条消息
        作用：反序列化消息并调用process_event
        Args:
            - stream_key: Stream键名
            - message_id: 消息ID
            - fields_bytes: 消息字段（bytes字典）
        """
        try:
            # 反序列化消息
            fields = {k.decode('utf-8'): v.decode('utf-8') for k, v in fields_bytes.items()}
            event_type_str = fields.get('event_type')

            if not event_type_str:
                logger.warning(f"消息缺少event_type字段: {message_id}")
                self._ack_message(stream_key, message_id)
                return

            # 根据event_type反序列化为对应的事件类
            event_type = EventType(event_type_str)
            event_class = EVENT_TYPE_MAP.get(event_type, BaseEvent)

            # 处理JSON字段（datetime需要特殊处理）
            if 'timestamp' in fields and isinstance(fields['timestamp'], str):
                fields['timestamp'] = datetime.fromisoformat(fields['timestamp'])

            # 处理复杂字段（JSON字符串）
            for key in ['tool_calls', 'metadata', 'tool_args', 'extracted_fields', 'confidence_scores', 'remaining_tasks', 'form_ids']:
                if key in fields and isinstance(fields[key], str):
                    try:
                        # 处理 'None' 字符串为 None
                        if fields[key] == 'None':
                            fields[key] = None
                        else:
                            fields[key] = json.loads(fields[key])
                    except json.JSONDecodeError:
                        pass

            event = event_class(**fields)

            # 调用子类的处理逻辑
            import asyncio
            asyncio.run(self.process_event(event))

            # 确认消息已处理
            self._ack_message(stream_key, message_id)

        except Exception as e:
            logger.error(f"消息处理失败: {message_id} -> {e}")
            # 不ACK失败的消息，让它进入pending列表，等待重试

    def _ack_message(self, stream_key: str, message_id: str):
        """确认消息已处理
        Args:
            - stream_key: Stream键名
            - message_id: 消息ID
        """
        try:
            self.redis.xack(stream_key, self.consumer_group, message_id)
            logger.debug(f"消息已确认: {message_id}")
        except Exception as e:
            logger.error(f"消息确认失败: {message_id} -> {e}")


class ScheduleAgentSubscriber(EventSubscriber):
    """Schedule Agent订阅器
    作用：订阅对话事件，检测偏离和工具调用完整性
    """

    def __init__(self, consumer_name: str = "schedule_agent"):
        super().__init__(
            consumer_group="schedule_agent_group",
            consumer_name=consumer_name
        )

    def get_stream_keys(self) -> List[str]:
        """获取所有活跃会话的dialog_stream键名
        Return:
            - stream_keys: dialog_stream:* 列表
        """
        # TODO: 从数据库查询活跃会话
        # 临时实现：扫描Redis所有dialog_stream:*键
        try:
            pattern = b"dialog_stream:*"
            keys = self.redis.client.keys(pattern)
            return [key.decode('utf-8') for key in keys]
        except Exception as e:
            logger.error(f"获取Stream键名失败: {e}")
            return []

    async def process_event(self, event: BaseEvent):
        """处理对话事件
        作用：检测偏离并发布约束提示
        Args:
            - event: 事件对象
        """
        logger.info(f"[Schedule Agent] 处理事件: {event.event_type} (session={event.session_id})")

        # TODO: 实现偏离检测逻辑
        # 1. 加载任务列表
        # 2. 检查对话是否偏离
        # 3. 检查工具调用完整性
        # 4. 发布约束提示事件


class ExtractionAgentSubscriber(EventSubscriber):
    """Field Extraction Agent订阅器
    作用：订阅对话事件，抽取结构化字段
    """

    def __init__(self, consumer_name: str = "extraction_agent"):
        super().__init__(
            consumer_group="extraction_agent_group",
            consumer_name=consumer_name
        )

    def get_stream_keys(self) -> List[str]:
        """获取所有活跃会话的dialog_stream键名"""
        try:
            pattern = b"dialog_stream:*"
            keys = self.redis.client.keys(pattern)
            return [key.decode('utf-8') for key in keys]
        except Exception as e:
            logger.error(f"获取Stream键名失败: {e}")
            return []

    async def process_event(self, event: BaseEvent):
        """处理对话事件
        作用：抽取字段并保存到数据库
        Args:
            - event: 事件对象
        """
        logger.info(f"[Extraction Agent] 处理事件: {event.event_type} (session={event.session_id})")

        # TODO: 实现字段抽取逻辑
        # 1. 读取对话历史
        # 2. 调用大模型抽取字段
        # 3. 保存到extracted_fields表
        # 4. 发布抽取结果事件


class SSESubscriber(EventSubscriber):
    """SSE推送订阅器
    作用：订阅对话事件，通过SSE推送到前端
    """

    def __init__(self, session_id: str):
        super().__init__(
            consumer_group=f"sse_group_{session_id}",
            consumer_name=f"sse_consumer_{session_id}"
        )
        self.session_id = session_id

    def get_stream_keys(self) -> List[str]:
        """只订阅指定会话的dialog_stream"""
        return [f"dialog_stream:{self.session_id}"]

    async def process_event(self, event: BaseEvent):
        """处理对话事件
        作用：将事件推送到SSE连接
        Args:
            - event: 事件对象
        """
        logger.debug(f"[SSE] 推送事件: {event.event_type} (session={event.session_id})")

        # TODO: 实现SSE推送逻辑（在API路由中实现）
