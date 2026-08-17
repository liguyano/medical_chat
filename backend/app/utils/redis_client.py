"""Redis客户端工具类
作用：提供Redis连接、Stream操作、缓存操作等功能
"""
import json
import pickle
from typing import Any, Dict, List, Optional, Tuple
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis同步客户端
    作用：提供Redis基础操作和Stream操作
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        """初始化Redis客户端
        Args:
            - host: Redis主机地址
            - port: Redis端口
            - db: 数据库编号
            - password: 密码
        """
        self.client = Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=False,  # Stream需要bytes模式
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        logger.info(f"Redis客户端初始化成功: {host}:{port}/{db}")

    def ping(self) -> bool:
        """检查Redis连接
        Return:
            - bool: 连接是否正常
        """
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            return False

    # ==================== Stream操作 ====================

    def xadd(self, stream_key: str, fields: Dict[str, Any], max_len: int = 10000) -> str:
        """向Stream添加消息
        作用：发布事件到Redis Stream
        Args:
            - stream_key: Stream键名
            - fields: 消息字段字典
            - max_len: Stream最大长度（超过则自动删除旧消息）
        Return:
            - message_id: 消息ID
        """
        # 序列化复杂对象为JSON
        serialized_fields = {}
        for key, value in fields.items():
            if isinstance(value, (dict, list)):
                serialized_fields[key] = json.dumps(value, ensure_ascii=False)
            else:
                serialized_fields[key] = str(value)

        message_id = self.client.xadd(
            stream_key,
            serialized_fields,
            maxlen=max_len,
            approximate=True  # 近似裁剪，性能更好
        )
        logger.debug(f"Stream发布成功: {stream_key} -> {message_id}")
        return message_id.decode('utf-8')

    def xread(
        self,
        streams: Dict[str, str],
        count: Optional[int] = None,
        block: Optional[int] = None
    ) -> List[Tuple[str, List[Tuple[str, Dict[str, bytes]]]]]:
        """从Stream读取消息
        作用：订阅事件流
        Args:
            - streams: {stream_key: last_id} 字典
            - count: 每次读取数量
            - block: 阻塞时间（毫秒），None表示非阻塞
        Return:
            - messages: [(stream_key, [(message_id, fields)])]
        """
        result = self.client.xread(streams=streams, count=count, block=block)
        return result

    def xgroup_create(self, stream_key: str, group_name: str, id: str = '0', mkstream: bool = True):
        """创建消费者组
        Args:
            - stream_key: Stream键名
            - group_name: 消费者组名称
            - id: 起始ID，'0'表示从头开始
            - mkstream: 如果Stream不存在是否创建
        """
        try:
            self.client.xgroup_create(stream_key, group_name, id=id, mkstream=mkstream)
            logger.info(f"消费者组创建成功: {group_name} @ {stream_key}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.warning(f"消费者组已存在: {group_name}")
            else:
                raise

    def xreadgroup(
        self,
        group_name: str,
        consumer_name: str,
        streams: Dict[str, str],
        count: Optional[int] = None,
        block: Optional[int] = None,
        noack: bool = False
    ) -> List[Tuple[bytes, List[Tuple[bytes, Dict[bytes, bytes]]]]]:
        """消费者组读取消息
        Args:
            - group_name: 消费者组名称
            - consumer_name: 消费者名称
            - streams: {stream_key: last_id} 字典，使用'>'表示读取未消费的消息
            - count: 每次读取数量
            - block: 阻塞时间（毫秒）
            - noack: 是否自动ACK
        Return:
            - messages: [(stream_key, [(message_id, fields)])]
        """
        result = self.client.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams=streams,
            count=count,
            block=block,
            noack=noack
        )
        return result

    def xack(self, stream_key: str, group_name: str, *message_ids):
        """确认消息已处理
        Args:
            - stream_key: Stream键名
            - group_name: 消费者组名称
            - message_ids: 消息ID列表
        """
        self.client.xack(stream_key, group_name, *message_ids)

    # ==================== 缓存操作 ====================

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """设置缓存
        Args:
            - key: 键名
            - value: 值（支持任意可序列化对象）
            - ex: 过期时间（秒）
        Return:
            - bool: 是否成功
        """
        try:
            serialized = pickle.dumps(value)
            return self.client.set(key, serialized, ex=ex)
        except Exception as e:
            logger.error(f"Redis SET失败: {key} -> {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """获取缓存
        Args:
            - key: 键名
        Return:
            - value: 反序列化后的值，不存在返回None
        """
        try:
            data = self.client.get(key)
            if data is None:
                return None
            return pickle.loads(data)
        except Exception as e:
            logger.error(f"Redis GET失败: {key} -> {e}")
            return None

    def delete(self, *keys: str) -> int:
        """删除缓存
        Args:
            - keys: 键名列表
        Return:
            - int: 删除成功的数量
        """
        return self.client.delete(*keys)

    def exists(self, *keys: str) -> int:
        """检查键是否存在
        Args:
            - keys: 键名列表
        Return:
            - int: 存在的数量
        """
        return self.client.exists(*keys)

    def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间
        Args:
            - key: 键名
            - seconds: 秒数
        Return:
            - bool: 是否成功
        """
        return self.client.expire(key, seconds)

    def ttl(self, key: str) -> int:
        """获取剩余过期时间
        Args:
            - key: 键名
        Return:
            - int: 剩余秒数，-1表示永不过期，-2表示不存在
        """
        return self.client.ttl(key)

    def close(self):
        """关闭连接"""
        self.client.close()


class AsyncRedisClient:
    """Redis异步客户端
    作用：提供异步Redis操作，用于FastAPI异步路由
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        """初始化异步Redis客户端"""
        self.client = AsyncRedis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        logger.info(f"异步Redis客户端初始化成功: {host}:{port}/{db}")

    async def ping(self) -> bool:
        """检查Redis连接"""
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            return False

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """异步设置缓存"""
        try:
            serialized = pickle.dumps(value)
            return await self.client.set(key, serialized, ex=ex)
        except Exception as e:
            logger.error(f"Redis SET失败: {key} -> {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """异步获取缓存"""
        try:
            data = await self.client.get(key)
            if data is None:
                return None
            return pickle.loads(data)
        except Exception as e:
            logger.error(f"Redis GET失败: {key} -> {e}")
            return None

    async def delete(self, *keys: str) -> int:
        """异步删除缓存"""
        return await self.client.delete(*keys)

    # ==================== Stream 操作（SSE 消费用） ====================

    async def xread(
        self,
        streams: Dict[str, str],
        count: Optional[int] = None,
        block: Optional[int] = None,
    ) -> List[Tuple[bytes, List[Tuple[bytes, Dict[bytes, bytes]]]]]:
        """异步从 Stream 读取消息
        作用：供 SSE 端点持续消费 dialog_stream，支持阻塞等待新消息。
        Args:
            - streams: {stream_key: last_id} 字典，last_id 之后的消息将被返回
            - count: 单次最多读取条数
            - block: 阻塞时间（毫秒），None 表示非阻塞
        Return:
            - messages: [(stream_key, [(message_id, fields)])]，无消息时为空列表
        """
        return await self.client.xread(streams=streams, count=count, block=block)

    # ==================== 分布式锁（对话并发控制用） ====================

    async def acquire_lock(self, key: str, token: str, ttl: int = 30) -> bool:
        """获取分布式锁
        作用：基于 SET NX PX 实现，防止同一会话并发处理消息。
        Args:
            - key: 锁键名，如 dialog_lock:{session_id}
            - token: 持有者标识（释放时校验，避免误删他人锁）
            - ttl: 锁过期秒数，防止持有者崩溃导致死锁
        Return:
            - bool: 是否成功获取
        """
        result = await self.client.set(key, token, nx=True, ex=ttl)
        return bool(result)

    async def release_lock(self, key: str, token: str) -> bool:
        """释放分布式锁
        作用：仅当锁归属该 token 时才删除，使用 Lua 脚本保证原子性。
        Args:
            - key: 锁键名
            - token: 持有者标识
        Return:
            - bool: 是否成功释放（token 不匹配返回 False）
        """
        lua = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        released = await self.client.eval(lua, 1, key, token)
        return bool(released)

    async def close(self):
        """关闭连接"""
        await self.client.close()


# 全局单例
redis_client: Optional[RedisClient] = None
async_redis_client: Optional[AsyncRedisClient] = None


def init_redis(host: str, port: int, db: int = 0, password: Optional[str] = None):
    """初始化全局Redis客户端
    作用：在应用启动时调用
    """
    global redis_client, async_redis_client
    redis_client = RedisClient(host=host, port=port, db=db, password=password)
    async_redis_client = AsyncRedisClient(host=host, port=port, db=db, password=password)
    logger.info("全局Redis客户端初始化完成")


def get_redis() -> RedisClient:
    """获取同步Redis客户端
    Return:
        - redis_client: Redis客户端实例
    """
    if redis_client is None:
        raise RuntimeError("Redis客户端未初始化，请先调用init_redis()")
    return redis_client


def get_async_redis() -> AsyncRedisClient:
    """获取异步Redis客户端
    Return:
        - async_redis_client: 异步Redis客户端实例
    """
    if async_redis_client is None:
        raise RuntimeError("异步Redis客户端未初始化，请先调用init_redis()")
    return async_redis_client
