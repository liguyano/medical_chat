"""Dialog Agent 核心编排
作用：DialogAgent 主逻辑，整合引擎、中间件、状态管理、事件发布。
"""
import logging
from typing import Any, Dict, List, Optional

from app.managers.agent_state_manager import AsyncAgentStateManager
from app.managers.assessment_loader import QuestionTask
from app.managers.dialog_history_manager import DialogHistoryManager

from ..middleware.base import MiddlewareChain
from ..middleware.event_publish import EventPublishMiddleware
from ..middleware.keyword_intercept import KeywordInterceptMiddleware
from ..middleware.schedule_constraint import ScheduleConstraintMiddleware
from ..middleware.timeout import TimeoutMiddleware
from .engine import DialogEngine
from .prompt import build_constraint_update_prompt, build_system_prompt
from .tools import DIALOG_TOOLS, execute_tool

logger = logging.getLogger(__name__)


class DialogAgent:
    """对话智能体
    作用：核心编排层，驱动对话引擎、执行中间件链、管理状态、发布事件。
    """

    def __init__(
        self,
        session_id: str,
        patient_info: Dict[str, Any],
        task_list: List[QuestionTask],
        engine: DialogEngine,
        session_factory=None,
    ):
        """初始化 Dialog Agent
        Args:
            - session_id: 会话 ID
            - patient_info: 患者信息（姓名、性别、年龄等）
            - task_list: 量表问题任务列表
            - engine: 对话引擎（DoubaoVoiceEngine / TextChatEngine）
            - session_factory: 数据库会话工厂（用于 DialogHistoryManager）
        """
        self.session_id = session_id
        self.patient_info = patient_info
        self.task_list = task_list
        self.engine = engine
        self.session_factory = session_factory

        # 轮次计数器
        self.turn_counter = 0

        # 状态管理器
        self.state_manager = AsyncAgentStateManager()
        self.history_manager = DialogHistoryManager(session_factory=session_factory)

        # 中间件链
        self.middleware = MiddlewareChain([
            KeywordInterceptMiddleware(session_factory=session_factory),
            ScheduleConstraintMiddleware(),
            EventPublishMiddleware(session_id=session_id),
            TimeoutMiddleware(timeout_minutes=5),
        ])

        logger.info(
            f"[DialogAgent] 初始化: session_id={session_id}, "
            f"任务数={len(task_list)}, 引擎={engine.__class__.__name__}"
        )

    async def initialize(self) -> None:
        """初始化对话引擎与会话
        作用：构建 system_prompt，创建引擎会话，保存初始状态到 Redis。
        """
        try:
            # 1. 构建 system_prompt
            system_prompt = build_system_prompt(
                patient_info=self.patient_info,
                task_list=self.task_list,
            )

            # 2. 创建引擎会话
            await self.engine.create_session(
                system_prompt=system_prompt,
                tools=DIALOG_TOOLS,
            )
            logger.info("[DialogAgent] 引擎会话已创建")

            # 3. 保存初始状态到 Redis
            initial_state = {
                "session_id": self.session_id,
                "patient_info": self.patient_info,
                "turn_counter": self.turn_counter,
                "engine_type": self.engine.__class__.__name__,
            }
            await self.state_manager.save_agent_state(
                session_id=self.session_id,
                state_data=initial_state,
            )
            logger.info("[DialogAgent] 初始状态已保存到 Redis")

        except Exception as e:
            logger.error(f"[DialogAgent] 初始化失败: {e}", exc_info=True)
            raise

    async def handle_patient_input(
        self,
        audio_or_text: Any,
        session_no: Optional[str] = None,
    ) -> str:
        """处理患者输入（主循环）
        作用：驱动引擎流式响应，分发事件，执行工具调用，运行中间件。
        Args:
            - audio_or_text: 患者输入（音频 bytes 或文本 str）
            - session_no: 业务会话号（用于 DialogHistoryManager）
        Return:
            - AI 完整回复文本
        """
        self.turn_counter += 1
        logger.info(f"[DialogAgent] 第 {self.turn_counter} 轮对话开始")

        # 上下文字典
        context = {
            "session_id": self.session_id,
            "turn_number": self.turn_counter,
            "patient_input": "",
            "constraints": [],
            "tool_calls": [],
        }

        try:
            # 1. 执行 before_agent 中间件
            await self.middleware.execute_before(context)

            # 2. 处理约束注入（如果中间件追加了约束）
            if context["constraints"]:
                constraint_prompt = build_constraint_update_prompt(context["constraints"])
                await self.engine.update_session(instructions=constraint_prompt)
                logger.info(f"[DialogAgent] 约束已注入: {len(context['constraints'])} 条")

            # 3. 发送患者输入到引擎
            await self.engine.send_input(audio_or_text)

            # 4. 流式接收 AI 响应
            full_response_text = ""
            async for event in self.engine.stream_response():
                event_type = event.get("type")

                # 4.1 用户语音识别结果
                if event_type == "user_transcript":
                    user_text = event.get("text", "")
                    context["patient_input"] = user_text
                    logger.info(f"[DialogAgent] 用户输入识别: {user_text}")

                    # 保存用户消息到 PG（如果提供了 session_no）
                    if session_no:
                        await self.history_manager.save_message(
                            session_no=session_no,
                            turn_no=self.turn_counter,
                            role_type="patient",
                            message_type="voice",
                            content_text=user_text,
                            asr_text=user_text,
                        )

                # 4.2 AI 文本增量
                elif event_type == "text":
                    content = event.get("content", "")
                    full_response_text += content
                    # 可在此处实时推送到前端（SSE）

                # 4.3 AI 语音增量
                elif event_type == "audio":
                    audio_data = event.get("data")
                    # TODO: 语音数据流式推送或保存

                # 4.4 工具调用
                elif event_type == "tool_call":
                    call_id = event.get("call_id")
                    tool_name = event.get("name")
                    tool_args = event.get("arguments", {})
                    logger.info(f"[DialogAgent] 工具调用: {tool_name}({tool_args})")

                    # 执行工具
                    tool_result = await execute_tool(tool_name, tool_args)

                    # 记录到 context
                    context["tool_calls"].append({
                        "call_id": call_id,
                        "name": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    })

                    # 回传结果到引擎
                    await self.engine.send_tool_result(call_id, tool_result)

                # 4.5 响应完成
                elif event_type == "response_done":
                    logger.info(f"[DialogAgent] AI 响应完成: {full_response_text[:100]}...")
                    break

                # 4.6 错误
                elif event_type == "error":
                    error_msg = event.get("message", "未知错误")
                    logger.error(f"[DialogAgent] 引擎错误: {error_msg}")
                    full_response_text = f"抱歉，系统遇到错误: {error_msg}"
                    break

            # 5. 保存 AI 消息到 PG
            if session_no and full_response_text:
                await self.history_manager.save_message(
                    session_no=session_no,
                    turn_no=self.turn_counter,
                    role_type="ai",
                    message_type="voice",
                    content_text=full_response_text,
                    tts_text=full_response_text,
                )

            # 6. 执行 after_agent 中间件（发布事件、更新超时）
            await self.middleware.execute_after(context, full_response_text)

            # 7. 更新 Redis 状态
            await self._update_state()

            return full_response_text

        except Exception as e:
            logger.error(f"[DialogAgent] 处理输入异常: {e}", exc_info=True)
            return f"抱歉，系统遇到异常: {str(e)}"

    async def _update_state(self) -> None:
        """更新 Redis 状态
        作用：每轮对话后同步轮次计数器到 Redis。
        """
        try:
            state_data = {
                "session_id": self.session_id,
                "turn_counter": self.turn_counter,
                "patient_info": self.patient_info,
            }
            await self.state_manager.save_agent_state(
                session_id=self.session_id,
                state_data=state_data,
            )
            logger.debug(f"[DialogAgent] 状态已更新: turn_counter={self.turn_counter}")

        except Exception as e:
            logger.error(f"[DialogAgent] 更新状态失败: {e}", exc_info=True)

    async def close(self) -> None:
        """关闭对话智能体
        作用：关闭引擎会话，清理 Redis 状态（可选保留）。
        """
        try:
            # 1. 关闭引擎会话
            await self.engine.close_session()
            logger.info("[DialogAgent] 引擎会话已关闭")

            # 2. 可选：删除 Redis 状态（保留用于恢复）
            # await self.state_manager.delete_agent_state(self.session_id)

        except Exception as e:
            logger.error(f"[DialogAgent] 关闭失败: {e}", exc_info=True)
