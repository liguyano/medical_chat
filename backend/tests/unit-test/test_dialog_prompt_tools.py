"""Dialog Agent 提示词与工具单元测试。"""

import pytest
from medagent.agents.service_agent.dialog_agent.prompt import (
    build_constraint_update_prompt,
    build_system_prompt,
)
from medagent.agents.service_agent.dialog_agent.tools import (
    DIALOG_TOOLS,
    execute_tool,
)
from medagent.agents.service_agent.schedule_agent import QuestionTask


def question(code="smoking", *, required=True):
    return QuestionTask(
        question_id=1,
        question_code=code,
        question_name="吸烟情况",
        patient_text="请问您是否吸烟？",
        question_type="单选",
        required=required,
        sort_no=1,
    )


def test_system_prompt_contains_cicare_patient_and_tasks():
    """系统提示词应包含护理规范、患者信息与评估任务。"""
    prompt = build_system_prompt(
        {
            "name": "张三",
            "gender": "男",
            "age": 60,
            "diagnosis_snapshot": {"primary": "慢性阻塞性肺疾病急性加重"},
        },
        [question(), question("optional", required=False)],
    )

    for stage in ("Connect", "Introduce", "Communicate", "Ask", "Respond", "Exit"):
        assert stage in prompt
    assert "张三" in prompt
    assert "[smoking]" in prompt
    assert "必填" in prompt
    assert "选填" in prompt
    assert "{patient_name}" not in prompt
    assert "TODO" not in prompt
    assert "只有系统确认全部必填评估进度完成后" in prompt
    assert "先接住患者当前内容" in prompt
    assert "禁止照抄" in prompt
    assert "开水房" in prompt
    assert "青霉素过敏" in prompt
    assert "慢性阻塞性肺疾病急性加重" in prompt
    assert "不得把诊断快照当作患者自述" in prompt
    assert "建议礼貌称呼：叔叔" in prompt
    assert "禁止每轮重复完整姓名" in prompt
    assert "get_education_material" not in prompt


def test_system_prompt_uses_safe_gender_and_age_salutation():
    """高龄女性应使用奶奶等自然昵称，未知性别不能武断猜称呼。"""
    elderly_prompt = build_system_prompt(
        {"name": "王奶奶", "gender": "女", "age": 80},
        [question()],
    )
    unknown_prompt = build_system_prompt(
        {"name": "患者", "gender": "未知", "age": 60},
        [question()],
    )

    assert "建议礼貌称呼：奶奶" in elderly_prompt
    assert "建议礼貌称呼：您" in unknown_prompt
    assert "您好，患者您" not in unknown_prompt


def test_system_prompt_includes_dynamic_constraints():
    """初始化时传入的约束必须进入 system prompt。"""
    prompt = build_system_prompt(
        {"name": "患者"},
        [question()],
        constraints=["不要重复询问已回答问题"],
    )

    assert "【当前约束】" in prompt
    assert "不要重复询问已回答问题" in prompt


def test_constraint_update_prompt_handles_empty_and_multiple_items():
    """动态约束提示应支持空列表和多条约束。"""
    assert build_constraint_update_prompt([]) == ""
    prompt = build_constraint_update_prompt(["回到评估", "调用宣教工具"])
    assert "【紧急约束】" in prompt
    assert "- 回到评估" in prompt
    assert "- 调用宣教工具" in prompt


def test_dialog_tool_schemas_follow_openai_function_contract():
    """四个工具 Schema 必须具备名称、对象参数和必填字段。"""
    assert len(DIALOG_TOOLS) == 3
    names = set()
    for tool in DIALOG_TOOLS:
        assert tool["type"] == "function"
        function = tool["function"]
        names.add(function["name"])
        assert function["parameters"]["type"] == "object"
        assert function["parameters"]["required"]
    assert names == {
        "trigger_consent_form",
        "request_nurse_assistance",
        "play_audio",
    }


@pytest.mark.asyncio
async def test_consent_returns_clauses_and_is_not_signed():
    """知情同意工具返回条款并保持待签署状态，form_id 必须避免固定碰撞。"""
    first = await execute_tool("trigger_consent_form", {"form_type": "surgery"})
    second = await execute_tool("trigger_consent_form", {"form_type": "surgery"})

    assert first["success"] is True
    assert first["status"] == "pending_signature"
    assert first["requires_signature"] is True
    assert first["clauses"]
    assert first["form_id"] != second["form_id"]


@pytest.mark.asyncio
async def test_tool_router_handles_unknown_and_invalid_arguments():
    """工具路由器应将未知工具和参数错误转换为结构化失败。"""
    unknown = await execute_tool("unknown", {})
    invalid = await execute_tool("get_education_material", {"unexpected": True})

    assert unknown["success"] is False
    assert invalid["success"] is False
    assert "参数错误" in invalid["message"]


@pytest.mark.asyncio
async def test_play_audio_is_explicitly_unavailable():
    """预留音频工具不得返回虚假的播放成功。"""
    result = await execute_tool("play_audio", {"audio_url": "https://example/audio"})

    assert result["success"] is False
    assert "领域组件接管" in result["message"]


@pytest.mark.asyncio
async def test_request_nurse_assistance_returns_action_and_reason():
    """呼叫护士工具返回可供患者端和护士端使用的结构化请求。"""
    result = await execute_tool(
        "request_nurse_assistance",
        {
            "requested_action": "measure_blood_pressure",
            "reason": "需要护士到床旁测量血压",
            "urgency": "urgent",
        },
    )
    assert result["success"] is True
    assert result["action_label"] == "测量血压"
    assert result["urgency"] == "urgent"
    assert result["status"] == "requested"
