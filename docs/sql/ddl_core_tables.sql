-- 医疗评估系统核心数据表DDL
-- 数据库: PostgreSQL 14+
-- 编码: UTF-8
-- 创建时间: 2026-08-16

-- ====================================
-- 1. 评估任务表
-- ====================================
CREATE TABLE assessment_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_no VARCHAR(32) UNIQUE NOT NULL,  -- 任务编号
    patient_id BIGINT NOT NULL,  -- 患者ID
    nurse_id BIGINT NOT NULL,  -- 创建任务的护士ID
    department_id BIGINT NOT NULL,  -- 科室ID
    form_ids JSONB NOT NULL,  -- 勾选的量表ID列表 ["form_1", "form_2"]
    task_type VARCHAR(20) NOT NULL,  -- 'questionnaire' | 'ai_dialog'
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending' | 'in_progress' | 'completed' | 'cancelled'
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,  -- 任务开始时间
    completed_at TIMESTAMP,  -- 任务完成时间
    CONSTRAINT chk_task_type CHECK (task_type IN ('questionnaire', 'ai_dialog')),
    CONSTRAINT chk_status CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled'))
);

CREATE INDEX idx_assessment_tasks_patient_id ON assessment_tasks(patient_id);
CREATE INDEX idx_assessment_tasks_nurse_id ON assessment_tasks(nurse_id);
CREATE INDEX idx_assessment_tasks_status ON assessment_tasks(status);
CREATE INDEX idx_assessment_tasks_created_at ON assessment_tasks(created_at DESC);

COMMENT ON TABLE assessment_tasks IS '评估任务主表';
COMMENT ON COLUMN assessment_tasks.task_no IS '任务编号，格式：TASK-{timestamp}-{random}';
COMMENT ON COLUMN assessment_tasks.form_ids IS '量表ID列表，JSON数组格式';


-- ====================================
-- 2. 对话会话表
-- ====================================
CREATE TABLE dialog_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) UNIQUE NOT NULL,  -- 会话ID（进程号）
    task_id BIGINT NOT NULL REFERENCES assessment_tasks(id) ON DELETE CASCADE,
    patient_id BIGINT NOT NULL,
    agent_type VARCHAR(50) NOT NULL,  -- 'schedule_agent' | 'dialog_agent' | 'extraction_agent'
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'preheating' | 'active' | 'paused' | 'completed' | 'error'
    redis_state_key VARCHAR(128),  -- Redis状态存储key: agent_state:{session_id}
    metadata JSONB,  -- 智能体元数据
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    CONSTRAINT chk_agent_type CHECK (agent_type IN ('schedule_agent', 'dialog_agent', 'extraction_agent')),
    CONSTRAINT chk_session_status CHECK (status IN ('preheating', 'active', 'paused', 'completed', 'error'))
);

CREATE INDEX idx_dialog_sessions_session_id ON dialog_sessions(session_id);
CREATE INDEX idx_dialog_sessions_task_id ON dialog_sessions(task_id);
CREATE INDEX idx_dialog_sessions_status ON dialog_sessions(status);
CREATE INDEX idx_dialog_sessions_last_active ON dialog_sessions(last_active_at DESC);

COMMENT ON TABLE dialog_sessions IS '对话会话表，记录各智能体会话状态';
COMMENT ON COLUMN dialog_sessions.redis_state_key IS 'Redis中存储智能体状态的key';
COMMENT ON COLUMN dialog_sessions.metadata IS '智能体元数据，包括配置参数、工具列表等';


-- ====================================
-- 3. 对话消息表
-- ====================================
CREATE TABLE dialog_messages (
    id BIGSERIAL PRIMARY KEY,
    message_id VARCHAR(64) UNIQUE NOT NULL,  -- 消息UUID
    session_id VARCHAR(64) NOT NULL REFERENCES dialog_sessions(session_id) ON DELETE CASCADE,
    turn_number INT NOT NULL,  -- 对话轮次，从1开始
    role VARCHAR(20) NOT NULL,  -- 'user' | 'assistant' | 'system' | 'tool'
    content TEXT NOT NULL,  -- 消息内容
    content_type VARCHAR(20) DEFAULT 'text',  -- 'text' | 'audio' | 'tool_call' | 'tool_result'
    tool_calls JSONB,  -- 工具调用记录 [{"name": "...", "args": {...}, "result": {...}}]
    audio_url VARCHAR(255),  -- 语音文件URL（如有）
    metadata JSONB,  -- 额外元数据（如：推理时长、token消耗等）
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_role CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    CONSTRAINT chk_content_type CHECK (content_type IN ('text', 'audio', 'tool_call', 'tool_result'))
);

CREATE INDEX idx_dialog_messages_session_id ON dialog_messages(session_id);
CREATE INDEX idx_dialog_messages_turn_number ON dialog_messages(session_id, turn_number);
CREATE INDEX idx_dialog_messages_created_at ON dialog_messages(created_at DESC);
CREATE INDEX idx_dialog_messages_role ON dialog_messages(role);

COMMENT ON TABLE dialog_messages IS '对话消息表，记录所有对话历史';
COMMENT ON COLUMN dialog_messages.turn_number IS '对话轮次，每一对user+assistant为一轮';
COMMENT ON COLUMN dialog_messages.tool_calls IS '工具调用详情，JSON数组格式';


-- ====================================
-- 4. 字段抽取结果表
-- ====================================
CREATE TABLE extracted_fields (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES dialog_sessions(session_id) ON DELETE CASCADE,
    form_id VARCHAR(50) NOT NULL,  -- 量表ID
    field_key VARCHAR(100) NOT NULL,  -- 字段键名
    field_value TEXT,  -- 字段值
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),  -- 抽取置信度 (0-1)
    source_message_id VARCHAR(64) REFERENCES dialog_messages(message_id) ON DELETE SET NULL,  -- 来源消息
    extraction_time TIMESTAMP NOT NULL DEFAULT NOW(),
    is_confirmed BOOLEAN DEFAULT FALSE,  -- 是否已人工确认
    confirmed_by BIGINT,  -- 确认人ID（护士）
    confirmed_at TIMESTAMP,
    CONSTRAINT uk_extracted_fields UNIQUE(session_id, form_id, field_key)
);

CREATE INDEX idx_extracted_fields_session_id ON extracted_fields(session_id);
CREATE INDEX idx_extracted_fields_form_id ON extracted_fields(form_id);
CREATE INDEX idx_extracted_fields_is_confirmed ON extracted_fields(is_confirmed);
CREATE INDEX idx_extracted_fields_confidence ON extracted_fields(confidence DESC);

COMMENT ON TABLE extracted_fields IS '字段抽取结果表，记录从对话中抽取的结构化字段';
COMMENT ON COLUMN extracted_fields.confidence IS '抽取置信度，低于0.7需要人工确认';


-- ====================================
-- 5. 智能体状态快照表
-- ====================================
CREATE TABLE agent_states (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES dialog_sessions(session_id) ON DELETE CASCADE,
    state_snapshot JSONB NOT NULL,  -- 智能体状态快照（序列化后的状态）
    snapshot_reason VARCHAR(50) NOT NULL,  -- 'periodic' | 'before_error' | 'manual'
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_snapshot_reason CHECK (snapshot_reason IN ('periodic', 'before_error', 'manual'))
);

CREATE INDEX idx_agent_states_session_id ON agent_states(session_id);
CREATE INDEX idx_agent_states_created_at ON agent_states(created_at DESC);

COMMENT ON TABLE agent_states IS '智能体状态快照表，用于故障恢复和调试';
COMMENT ON COLUMN agent_states.snapshot_reason IS '快照原因：定期备份、错误前保存、手动触发';


-- ====================================
-- 6. 护理评分表
-- ====================================
CREATE TABLE nurse_ratings (
    id BIGSERIAL PRIMARY KEY,
    message_id VARCHAR(64) NOT NULL REFERENCES dialog_messages(message_id) ON DELETE CASCADE,
    nurse_id BIGINT NOT NULL,
    rating_type VARCHAR(20) NOT NULL,  -- 'like' | 'dislike'
    comment TEXT,  -- 护士意见
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_rating_type CHECK (rating_type IN ('like', 'dislike'))
);

CREATE INDEX idx_nurse_ratings_message_id ON nurse_ratings(message_id);
CREATE INDEX idx_nurse_ratings_nurse_id ON nurse_ratings(nurse_id);
CREATE INDEX idx_nurse_ratings_rating_type ON nurse_ratings(rating_type);
CREATE INDEX idx_nurse_ratings_created_at ON nurse_ratings(created_at DESC);

COMMENT ON TABLE nurse_ratings IS '护理评分表，用于收集护士对AI对话的反馈';


-- ====================================
-- 7. 宣教记录表
-- ====================================
CREATE TABLE education_records (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES dialog_sessions(session_id) ON DELETE CASCADE,
    message_id VARCHAR(64) REFERENCES dialog_messages(message_id) ON DELETE SET NULL,
    education_type VARCHAR(50) NOT NULL,  -- 'tobacco' | 'alcohol' | 'diabetes' | 'allergy' ...
    material_id VARCHAR(50) NOT NULL,  -- 宣教材料ID
    level INT CHECK (level >= 1 AND level <= 3),  -- 宣教级别 (1-3)
    is_completed BOOLEAN DEFAULT FALSE,  -- 是否完成宣读
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX idx_education_records_session_id ON education_records(session_id);
CREATE INDEX idx_education_records_education_type ON education_records(education_type);
CREATE INDEX idx_education_records_is_completed ON education_records(is_completed);

COMMENT ON TABLE education_records IS '宣教记录表，记录分级宣教执行情况';
COMMENT ON COLUMN education_records.level IS '宣教级别：1-基础宣教，2-详细宣教，3-重点宣教';


-- ====================================
-- 8. 知情同意书签署表
-- ====================================
CREATE TABLE consent_forms (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES dialog_sessions(session_id) ON DELETE CASCADE,
    message_id VARCHAR(64) REFERENCES dialog_messages(message_id) ON DELETE SET NULL,
    form_type VARCHAR(50) NOT NULL,  -- 'surgery' | 'anesthesia' | 'blood_transfusion' | 'tobacco' ...
    form_content TEXT NOT NULL,  -- 知情同意书内容
    is_signed BOOLEAN DEFAULT FALSE,  -- 是否已签署
    signature_data TEXT,  -- 签名图片base64或URL
    signed_at TIMESTAMP
);

CREATE INDEX idx_consent_forms_session_id ON consent_forms(session_id);
CREATE INDEX idx_consent_forms_form_type ON consent_forms(form_type);
CREATE INDEX idx_consent_forms_is_signed ON consent_forms(is_signed);

COMMENT ON TABLE consent_forms IS '知情同意书签署表';
COMMENT ON COLUMN consent_forms.signature_data IS '患者签名数据，可以是base64图片或OSS URL';


-- ====================================
-- 触发器：自动更新last_active_at
-- ====================================
CREATE OR REPLACE FUNCTION update_session_last_active()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE dialog_sessions
    SET last_active_at = NOW()
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_session_last_active
AFTER INSERT ON dialog_messages
FOR EACH ROW
EXECUTE FUNCTION update_session_last_active();

COMMENT ON FUNCTION update_session_last_active IS '触发器函数：每次插入消息时更新会话最后活跃时间';


-- ====================================
-- 视图：评估任务进度统计
-- ====================================
CREATE OR REPLACE VIEW v_task_progress AS
SELECT
    t.id AS task_id,
    t.task_no,
    t.patient_id,
    t.nurse_id,
    t.status,
    ds.session_id,
    COUNT(DISTINCT ef.field_key) AS completed_fields,
    COALESCE(
        (SELECT COUNT(*)
         FROM jsonb_array_elements_text(t.form_ids) AS form_id,
         LATERAL (SELECT COUNT(*) FROM unnest(ARRAY['field1', 'field2']) AS field) AS total_fields),
        0
    ) AS total_fields,
    ROUND(
        CAST(COUNT(DISTINCT ef.field_key) AS NUMERIC) /
        NULLIF(
            (SELECT COUNT(*)
             FROM jsonb_array_elements_text(t.form_ids)),
            0
        ) * 100,
        2
    ) AS progress_percentage
FROM assessment_tasks t
LEFT JOIN dialog_sessions ds ON ds.task_id = t.id AND ds.agent_type = 'dialog_agent'
LEFT JOIN extracted_fields ef ON ef.session_id = ds.session_id
WHERE t.task_type = 'ai_dialog'
GROUP BY t.id, t.task_no, t.patient_id, t.nurse_id, t.status, ds.session_id;

COMMENT ON VIEW v_task_progress IS '评估任务进度统计视图';
