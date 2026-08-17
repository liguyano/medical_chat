"""Middleware 基础抽象与链式执行器
作用：定义 DialogMiddleware 抽象基类和 MiddlewareChain 执行器。
"""
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class DialogMiddleware(ABC):
    """对话中间件抽象基类
    作用：定义 before_agent / after_agent 生命周期钩子。
    """

    @abstractmethod
    async def before_agent(self, context: dict[str, Any]) -> None:
        """智能体执行前钩子
        作用：在对话处理前执行，可修改 context 注入约束、检查关键词等。
        Args:
            - context: 上下文字典，包含 session_id、patient_input、constraints 等
        """

    @abstractmethod
    async def after_agent(self, context: dict[str, Any], output: Any) -> None:
        """智能体执行后钩子
        作用：在对话处理后执行，用于事件发布、超时检测等。
        Args:
            - context: 上下文字典
            - output: 智能体输出（AI 回复文本或结构化数据）
        """


class MiddlewareChain:
    """中间件链执行器
    作用：按顺序执行多个中间件，异常隔离（单个中间件失败不阻塞链）。
    """

    def __init__(self, middlewares: list[DialogMiddleware]):
        """初始化中间件链
        Args:
            - middlewares: 中间件列表（按注册顺序执行）
        """
        self.middlewares = middlewares
        logger.info(f"[MiddlewareChain] 初始化: 共 {len(middlewares)} 个中间件")

    async def execute_before(self, context: dict[str, Any]) -> None:
        """执行所有中间件的 before_agent 钩子
        作用：顺序调用，捕获并记录异常，不中断链。
        Args:
            - context: 上下文字典
        """
        for middleware in self.middlewares:
            try:
                await middleware.before_agent(context)
            except Exception:
                logger.exception(
                    "[MiddlewareChain] before_agent 异常: %s",
                    middleware.__class__.__name__,
                )

    async def execute_after(self, context: dict[str, Any], output: Any) -> None:
        """执行所有中间件的 after_agent 钩子
        作用：顺序调用，捕获并记录异常，不中断链。
        Args:
            - context: 上下文字典
            - output: 智能体输出
        """
        for middleware in self.middlewares:
            try:
                await middleware.after_agent(context, output)
            except Exception:
                logger.exception(
                    "[MiddlewareChain] after_agent 异常: %s",
                    middleware.__class__.__name__,
                )
