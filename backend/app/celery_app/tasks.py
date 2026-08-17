"""Celery任务定义
作用：定义三个智能体的后台任务，以及定时清理、测试任务。
说明：所有任务均注册到 celery_config 中的全局唯一 celery_app 实例。
"""
import logging

from app.celery_app.celery_config import celery_app

logger = logging.getLogger(__name__)


# ==================== Schedule Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.schedule_agent_worker", bind=True)
def schedule_agent_worker(self, session_id: str, task_config: dict):
    """Schedule Agent后台任务
    作用：调度智能体，监控对话进度，检测偏离，注入约束
    Args:
        - session_id: 会话ID
        - task_config: 任务配置（包含量表ID列表等）
    """
    try:
        logger.info(f"[Schedule Agent] 启动任务: session_id={session_id}")

        # TODO: 实现Schedule Agent逻辑
        # 1. 生成任务列表（量表问题列表）
        # 2. 订阅dialog_stream事件
        # 3. 检测对话偏离
        # 4. 检查工具调用完整性
        # 5. 发布约束提示到Redis Stream

        logger.info(f"[Schedule Agent] 任务完成: session_id={session_id}")
        return {"status": "completed", "session_id": session_id}

    except Exception as e:
        logger.error(f"[Schedule Agent] 任务失败: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)


# ==================== Dialog Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.dialog_agent_preheat", bind=True)
def dialog_agent_preheat(self, session_id: str, patient_info: dict):
    """Dialog Agent预热任务
    作用：创建WebSocket连接，初始化豆包语音会话
    Args:
        - session_id: 会话ID
        - patient_info: 患者信息（用于个性化提示词）
    """
    try:
        logger.info(f"[Dialog Agent] 预热任务启动: session_id={session_id}")

        # TODO: 实现Dialog Agent预热逻辑
        # 1. 创建DoubaoVoiceEngine实例
        # 2. 建立WebSocket连接
        # 3. 初始化系统提示词
        # 4. 注册工具列表（宣教、知情同意书）
        # 5. 保存智能体状态到Redis

        logger.info(f"[Dialog Agent] 预热完成: session_id={session_id}")
        return {"status": "preheated", "session_id": session_id}

    except Exception as e:
        logger.error(f"[Dialog Agent] 预热失败: {e}")
        raise self.retry(exc=e, countdown=5, max_retries=3)


# ==================== Field Extraction Agent任务 ====================

@celery_app.task(name="app.celery_app.tasks.extraction_agent_worker", bind=True)
def extraction_agent_worker(self, session_id: str, form_ids: list):
    """Field Extraction Agent后台任务
    作用：从对话历史中抽取结构化字段
    Args:
        - session_id: 会话ID
        - form_ids: 量表ID列表
    """
    try:
        logger.info(f"[Extraction Agent] 启动任务: session_id={session_id}")

        # TODO: 实现Field Extraction Agent逻辑
        # 1. 订阅dialog_stream事件
        # 2. 批量读取对话历史
        # 3. 调用大模型抽取字段
        # 4. 计算置信度
        # 5. 保存为 assessment_submission + assessment_answer
        # 6. 发布进度更新事件

        logger.info(f"[Extraction Agent] 任务完成: session_id={session_id}")
        return {"status": "completed", "session_id": session_id}

    except Exception as e:
        logger.error(f"[Extraction Agent] 任务失败: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)


# ==================== 定时任务 ====================

@celery_app.task(name="app.celery_app.tasks.cleanup_expired_sessions")
def cleanup_expired_sessions():
    """清理过期会话
    作用：定期清理超时未活跃的会话
    """
    try:
        logger.info("[定时任务] 清理过期会话")

        # TODO: 实现清理逻辑
        # 1. 查询超过5分钟无活跃的会话（last_active_at）
        # 2. 标记为paused状态
        # 3. 推送护士通知
        # 4. 清理Redis中的智能体状态

        return {"status": "completed"}

    except Exception as e:
        logger.error(f"[定时任务] 清理失败: {e}")
        raise


# ==================== 测试任务 ====================

@celery_app.task(name="app.celery_app.tasks.test_task")
def test_task(x: int, y: int):
    """测试任务
    作用：验证Celery配置是否正常
    """
    logger.info(f"[测试任务] 执行: {x} + {y}")
    result = x + y
    logger.info(f"[测试任务] 结果: {result}")
    return result
