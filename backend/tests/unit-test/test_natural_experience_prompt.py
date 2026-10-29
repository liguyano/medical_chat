from medagent.agents.service_agent.dialog_agent.prompt import build_system_prompt


def test_text_and_actual_voice_share_experience_policy():
    text = build_system_prompt(patient_info={}, task_list=[])
    for prompt in (text,):
        assert "【自然经历式接话】" in prompt
        assert "不能逐段照演" in prompt
        assert "患者追问时如实解释" in prompt
        assert "明确证据不足保持缺失" in prompt


def test_unanswered_turns_receive_response_without_invented_facts_or_repetition():
    for prompt in (build_system_prompt(patient_info={}, task_list=[]),):
        assert "【未答所问也接话】" in prompt
        assert "不要求每轮必须产生护理答案" in prompt
        assert "不得原句重复上一轮问题" in prompt
        assert "禁止靠重复问题催答" in prompt
        assert "转写语义不通或指代不明" in prompt
