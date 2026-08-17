"""medagent 模型供应商层
作用：提供统一的模型工厂入口，封装 BaseChatModel 与语音引擎的实例化逻辑。
"""
from medagent.providers.llm_model import create_chat_model, create_voice_engine

__all__ = ["create_chat_model", "create_voice_engine"]
