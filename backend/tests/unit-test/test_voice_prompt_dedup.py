from medagent.agents.service_agent.dialog_agent.prompt import build_system_prompt
from medagent.agents.service_agent.schedule_agent import QuestionTask

from app.services.voice_gateway import VoiceGateway


def test_voice_has_one_fact_copy_and_no_second_numbered_task_list():
    task = QuestionTask(
        question_id=1,
        question_code="unique_fact",
        question_name="测试事实",
        patient_text="过去24小时特定动作的唯一条件",
        question_type="文本",
        required=True,
        sort_no=1,
    )
    prompt = VoiceGateway._build_remaining_assessment_instructions({}, [task])
    assert prompt.count(task.patient_text) == 1
    assert "【评估任务列表】" not in prompt
    assert "【剩余题完整结构】" not in prompt
    assert "【评估任务列表】" in build_system_prompt({}, [task])
    assert "request_assessment_finish" in prompt
