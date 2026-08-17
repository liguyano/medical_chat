"""智能体状态管理器
作用：管理智能体运行态的 Redis 存储与 TTL。
说明：数据库事实来源已废弃 agent_states 表；可审计业务数据由 interaction/assessment 域持久化。
"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from app.utils.redis_client import get_redis, get_async_redis

logger = logging.getLogger(__name__)


class AgentStateManager:
    """智能体状态管理器
    作用：序列化智能体状态到Redis，按需加载
    """

    def __init__(self):
        """初始化状态管理器"""
        self.redis = get_redis()
        self.state_ttl = 3600  # 状态存活时间：1小时

    def _get_state_key(self, session_id: str) -> str:
        """生成状态键名
        Args:
            - session_id: 会话ID
        Return:
            - key: agent_state:{session_id}
        """
        return f"agent_state:{session_id}"

    def save_agent_state(self, session_id: str, agent_state: Dict[str, Any]) -> bool:
        """保存智能体状态到Redis
        作用：序列化智能体状态，TTL=1小时
        Args:
            - session_id: 会话ID
            - agent_state: 智能体状态字典
                {
                    "system_prompt": str,
                    "tools": List[str],
                    "memory": Dict,
                    "context": Dict,
                    "metadata": Dict,
                    "created_at": datetime,
                    "updated_at": datetime
                }
        Return:
            - bool: 是否成功
        """
        try:
            state_key = self._get_state_key(session_id)

            # 添加时间戳
            agent_state["updated_at"] = datetime.now()
            if "created_at" not in agent_state:
                agent_state["created_at"] = datetime.now()

            # 序列化并保存
            success = self.redis.set(state_key, agent_state, ex=self.state_ttl)

            if success:
                logger.info(f"智能体状态保存成功: {session_id}")
            else:
                logger.error(f"智能体状态保存失败: {session_id}")

            return success
        except Exception as e:
            logger.error(f"保存智能体状态异常: {session_id} -> {e}")
            return False

    def load_agent_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从Redis加载智能体状态
        Args:
            - session_id: 会话ID
        Return:
            - agent_state: 智能体状态字典，不存在返回None
        """
        try:
            state_key = self._get_state_key(session_id)
            agent_state = self.redis.get(state_key)

            if agent_state is None:
                logger.warning(f"Redis中未找到智能体状态: {session_id}")
            else:
                logger.info(f"智能体状态加载成功: {session_id}")

            return agent_state
        except Exception as e:
            logger.error(f"加载智能体状态异常: {session_id} -> {e}")
            return None

    def delete_agent_state(self, session_id: str) -> bool:
        """删除智能体状态
        作用：会话结束时清理Redis状态
        Args:
            - session_id: 会话ID
        Return:
            - bool: 是否成功
        """
        try:
            state_key = self._get_state_key(session_id)
            deleted_count = self.redis.delete(state_key)

            if deleted_count > 0:
                logger.info(f"智能体状态删除成功: {session_id}")
                return True
            else:
                logger.warning(f"智能体状态不存在: {session_id}")
                return False
        except Exception as e:
            logger.error(f"删除智能体状态异常: {session_id} -> {e}")
            return False

    def exists(self, session_id: str) -> bool:
        """检查智能体状态是否存在
        Args:
            - session_id: 会话ID
        Return:
            - bool: 是否存在
        """
        try:
            state_key = self._get_state_key(session_id)
            return self.redis.exists(state_key) > 0
        except Exception as e:
            logger.error(f"检查智能体状态异常: {session_id} -> {e}")
            return False

    def extend_ttl(self, session_id: str) -> bool:
        """延长智能体状态过期时间
        作用：活跃会话延长TTL，避免频繁重建
        Args:
            - session_id: 会话ID
        Return:
            - bool: 是否成功
        """
        try:
            state_key = self._get_state_key(session_id)
            return self.redis.expire(state_key, self.state_ttl)
        except Exception as e:
            logger.error(f"延长智能体状态TTL异常: {session_id} -> {e}")
            return False

    def get_ttl(self, session_id: str) -> int:
        """获取智能体状态剩余TTL
        Args:
            - session_id: 会话ID
        Return:
            - int: 剩余秒数，-1表示永不过期，-2表示不存在
        """
        try:
            state_key = self._get_state_key(session_id)
            return self.redis.ttl(state_key)
        except Exception as e:
            logger.error(f"获取智能体状态TTL异常: {session_id} -> {e}")
            return -2

class AsyncAgentStateManager:
    """异步智能体状态管理器
    作用：提供异步API，用于FastAPI异步路由
    """

    def __init__(self):
        """初始化异步状态管理器"""
        self.redis = get_async_redis()
        self.state_ttl = 3600

    def _get_state_key(self, session_id: str) -> str:
        """生成状态键名"""
        return f"agent_state:{session_id}"

    async def save_agent_state(self, session_id: str, agent_state: Dict[str, Any]) -> bool:
        """异步保存智能体状态"""
        try:
            state_key = self._get_state_key(session_id)

            agent_state["updated_at"] = datetime.now()
            if "created_at" not in agent_state:
                agent_state["created_at"] = datetime.now()

            success = await self.redis.set(state_key, agent_state, ex=self.state_ttl)

            if success:
                logger.info(f"智能体状态保存成功（异步）: {session_id}")
            else:
                logger.error(f"智能体状态保存失败（异步）: {session_id}")

            return success
        except Exception as e:
            logger.error(f"保存智能体状态异常（异步）: {session_id} -> {e}")
            return False

    async def load_agent_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """异步加载智能体状态"""
        try:
            state_key = self._get_state_key(session_id)
            agent_state = await self.redis.get(state_key)

            if agent_state is None:
                logger.warning(f"Redis中未找到智能体状态（异步）: {session_id}")
            else:
                logger.info(f"智能体状态加载成功（异步）: {session_id}")

            return agent_state
        except Exception as e:
            logger.error(f"加载智能体状态异常（异步）: {session_id} -> {e}")
            return None

    async def delete_agent_state(self, session_id: str) -> bool:
        """异步删除智能体状态"""
        try:
            state_key = self._get_state_key(session_id)
            deleted_count = await self.redis.delete(state_key)

            if deleted_count > 0:
                logger.info(f"智能体状态删除成功（异步）: {session_id}")
                return True
            else:
                logger.warning(f"智能体状态不存在（异步）: {session_id}")
                return False
        except Exception as e:
            logger.error(f"删除智能体状态异常（异步）: {session_id} -> {e}")
            return False
