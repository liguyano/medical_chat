"""会话超时管理器
作用：检测患者无响应，自动暂停会话，推送通知
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
import asyncio

from app.utils.redis_client import get_redis, get_async_redis

logger = logging.getLogger(__name__)


class SessionTimeoutManager:
    """会话超时管理器
    作用：检测患者无响应超时，自动暂停会话
    """

    def __init__(self, timeout_minutes: int = 5):
        """初始化超时管理器
        Args:
            - timeout_minutes: 超时时间（分钟），默认5分钟
        """
        self.redis = get_redis()
        self.timeout_seconds = timeout_minutes * 60

    def _get_activity_key(self, session_id: str) -> str:
        """生成活跃时间键名
        Args:
            - session_id: 会话ID
        Return:
            - key: session_activity:{session_id}
        """
        return f"session_activity:{session_id}"

    def update_activity(self, session_id: str) -> bool:
        """更新会话活跃时间
        作用：每次患者交互时调用，刷新活跃时间戳
        Args:
            - session_id: 会话ID
        Return:
            - bool: 是否成功
        """
        try:
            activity_key = self._get_activity_key(session_id)
            current_time = datetime.now().isoformat()

            # 设置活跃时间，TTL稍长于超时时间（+1分钟）
            success = self.redis.set(
                activity_key,
                current_time,
                ex=self.timeout_seconds + 60
            )

            if success:
                logger.debug(f"会话活跃时间更新: {session_id}")
            return success
        except Exception as e:
            logger.error(f"更新会话活跃时间异常: {session_id} -> {e}")
            return False

    def get_last_activity(self, session_id: str) -> Optional[datetime]:
        """获取最后活跃时间
        Args:
            - session_id: 会话ID
        Return:
            - datetime: 最后活跃时间，不存在返回None
        """
        try:
            activity_key = self._get_activity_key(session_id)
            activity_time_str = self.redis.get(activity_key)

            if activity_time_str is None:
                return None

            return datetime.fromisoformat(activity_time_str)
        except Exception as e:
            logger.error(f"获取会话活跃时间异常: {session_id} -> {e}")
            return None

    def is_timeout(self, session_id: str) -> bool:
        """检查会话是否超时
        Args:
            - session_id: 会话ID
        Return:
            - bool: 是否超时
        """
        try:
            last_activity = self.get_last_activity(session_id)

            if last_activity is None:
                logger.warning(f"会话无活跃记录: {session_id}")
                return True

            elapsed = (datetime.now() - last_activity).total_seconds()
            is_timeout = elapsed > self.timeout_seconds

            if is_timeout:
                logger.warning(
                    f"会话超时检测: {session_id} "
                    f"elapsed={elapsed:.1f}s timeout={self.timeout_seconds}s"
                )

            return is_timeout
        except Exception as e:
            logger.error(f"检查会话超时异常: {session_id} -> {e}")
            return False

    def get_remaining_time(self, session_id: str) -> int:
        """获取剩余活跃时间（秒）
        Args:
            - session_id: 会话ID
        Return:
            - int: 剩余秒数，已超时返回0，不存在返回-1
        """
        try:
            last_activity = self.get_last_activity(session_id)

            if last_activity is None:
                return -1

            elapsed = (datetime.now() - last_activity).total_seconds()
            remaining = max(0, self.timeout_seconds - elapsed)

            return int(remaining)
        except Exception as e:
            logger.error(f"获取剩余活跃时间异常: {session_id} -> {e}")
            return -1

    def clear_activity(self, session_id: str) -> bool:
        """清除会话活跃记录
        作用：会话结束时调用
        Args:
            - session_id: 会话ID
        Return:
            - bool: 是否成功
        """
        try:
            activity_key = self._get_activity_key(session_id)
            deleted_count = self.redis.delete(activity_key)

            if deleted_count > 0:
                logger.info(f"会话活跃记录清除成功: {session_id}")
                return True
            else:
                logger.warning(f"会话活跃记录不存在: {session_id}")
                return False
        except Exception as e:
            logger.error(f"清除会话活跃记录异常: {session_id} -> {e}")
            return False


class AsyncSessionTimeoutManager:
    """异步会话超时管理器
    作用：提供异步API，用于FastAPI异步路由
    """

    def __init__(self, timeout_minutes: int = 5):
        """初始化异步超时管理器"""
        self.redis = get_async_redis()
        self.timeout_seconds = timeout_minutes * 60

    def _get_activity_key(self, session_id: str) -> str:
        """生成活跃时间键名"""
        return f"session_activity:{session_id}"

    async def update_activity(self, session_id: str) -> bool:
        """异步更新会话活跃时间"""
        try:
            activity_key = self._get_activity_key(session_id)
            current_time = datetime.now().isoformat()

            success = await self.redis.set(
                activity_key,
                current_time,
                ex=self.timeout_seconds + 60
            )

            if success:
                logger.debug(f"会话活跃时间更新（异步）: {session_id}")
            return success
        except Exception as e:
            logger.error(f"更新会话活跃时间异常（异步）: {session_id} -> {e}")
            return False

    async def get_last_activity(self, session_id: str) -> Optional[datetime]:
        """异步获取最后活跃时间"""
        try:
            activity_key = self._get_activity_key(session_id)
            activity_time_str = await self.redis.get(activity_key)

            if activity_time_str is None:
                return None

            return datetime.fromisoformat(activity_time_str)
        except Exception as e:
            logger.error(f"获取会话活跃时间异常（异步）: {session_id} -> {e}")
            return None

    async def is_timeout(self, session_id: str) -> bool:
        """异步检查会话是否超时"""
        try:
            last_activity = await self.get_last_activity(session_id)

            if last_activity is None:
                logger.warning(f"会话无活跃记录（异步）: {session_id}")
                return True

            elapsed = (datetime.now() - last_activity).total_seconds()
            is_timeout = elapsed > self.timeout_seconds

            if is_timeout:
                logger.warning(
                    f"会话超时检测（异步）: {session_id} "
                    f"elapsed={elapsed:.1f}s timeout={self.timeout_seconds}s"
                )

            return is_timeout
        except Exception as e:
            logger.error(f"检查会话超时异常（异步）: {session_id} -> {e}")
            return False

    async def get_remaining_time(self, session_id: str) -> int:
        """异步获取剩余活跃时间"""
        try:
            last_activity = await self.get_last_activity(session_id)

            if last_activity is None:
                return -1

            elapsed = (datetime.now() - last_activity).total_seconds()
            remaining = max(0, self.timeout_seconds - elapsed)

            return int(remaining)
        except Exception as e:
            logger.error(f"获取剩余活跃时间异常（异步）: {session_id} -> {e}")
            return -1


class TimeoutMonitor:
    """超时监控器
    作用：后台定时扫描超时会话，自动暂停并推送通知
    """

    def __init__(self, check_interval: int = 30):
        """初始化超时监控器
        Args:
            - check_interval: 检查间隔（秒），默认30秒
        """
        self.check_interval = check_interval
        self.timeout_manager = SessionTimeoutManager()
        self.running = False

    async def start_monitoring(self):
        """启动后台监控
        作用：定期扫描所有活跃会话，检测超时
        """
        self.running = True
        logger.info("超时监控器启动")

        while self.running:
            try:
                await self._check_all_sessions()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"超时监控异常: {e}")
                await asyncio.sleep(self.check_interval)

    async def stop_monitoring(self):
        """停止后台监控"""
        self.running = False
        logger.info("超时监控器停止")

    async def _check_all_sessions(self):
        """检查所有活跃会话
        作用：扫描Redis中所有session_activity:*键
        """
        try:
            # TODO: 从数据库查询所有活跃会话ID
            # 目前暂时扫描Redis键（性能较低）
            redis = self.timeout_manager.redis
            pattern = b"session_activity:*"
            keys = redis.client.keys(pattern)

            for key in keys:
                session_id = key.decode('utf-8').replace("session_activity:", "")
                if self.timeout_manager.is_timeout(session_id):
                    await self._handle_timeout(session_id)

        except Exception as e:
            logger.error(f"检查所有会话异常: {e}")

    async def _handle_timeout(self, session_id: str):
        """处理超时会话
        Args:
            - session_id: 会话ID
        """
        try:
            logger.warning(f"会话超时处理: {session_id}")

            # TODO: 实现超时处理逻辑
            # 1. 更新会话状态为"paused"
            # 2. 推送通知到护士端
            # 3. 发布超时事件到Redis Stream
            # 4. 记录超时日志到数据库

            # 示例：发布超时事件（需要DialogEventPublisher）
            # from app.workers.event_publisher import DialogEventPublisher
            # publisher = DialogEventPublisher(session_id)
            # event = SessionTimeoutEvent(session_id=session_id, timeout_at=datetime.now())
            # publisher.publish(event)

        except Exception as e:
            logger.error(f"处理超时会话异常: {session_id} -> {e}")
