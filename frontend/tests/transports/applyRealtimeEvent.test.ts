import { afterEach, describe, expect, it, vi } from 'vitest';

describe('实时事件进度口径', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('患者发言不推进评估进度，只有progress_updated可以推进', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    const { useChatStore } = await import('@/lib/stores/useChatStore');
    const { useTaskStore } = await import('@/lib/stores/useTaskStore');
    const { applyRealtimeEvent } = await import(
      '@/lib/transports/applyRealtimeEvent'
    );
    const task = useTaskStore.getState().tasks[0];
    useTaskStore.setState({
      tasks: [{ ...task, id: '68', progress: { current: 2, total: 10 } }],
    });
    useChatStore.setState({
      sessions: {
        '68': {
          id: 'SESS-68',
          sessionNo: 'SESS-68',
          taskId: '68',
          patientId: '1',
          encounterId: '1',
          interactionType: 'assessment',
          channelType: 'text',
          sessionStatus: 'active',
          currentCicareStage: 'ask',
          answeredQuestionCount: 2,
          totalQuestionCount: 10,
          messages: [],
        },
      },
    });

    applyRealtimeEvent({
      event_id: '1-0',
      event_type: 'user_transcript_completed',
      task_id: '68',
      session_id: 'SESS-68',
      message_id: 'PATIENT-1',
      occurred_at: new Date().toISOString(),
      payload: { content_text: '我的回答', turn_no: 3 },
    });

    expect(
      useChatStore.getState().sessions['68'].answeredQuestionCount
    ).toBe(2);
    expect(useTaskStore.getState().tasks[0].progress).toEqual({
      current: 2,
      total: 10,
    });

    applyRealtimeEvent({
      event_id: '2-0',
      event_type: 'progress_updated',
      task_id: '68',
      session_id: 'SESS-68',
      occurred_at: new Date().toISOString(),
      payload: { current: 3, total: 10, completed: false },
    });

    expect(
      useChatStore.getState().sessions['68'].answeredQuestionCount
    ).toBe(3);
    expect(useTaskStore.getState().tasks[0].progress).toEqual({
      current: 3,
      total: 10,
    });
  });

  it('把工具领域事件写入宣教、同意和护士呼叫状态', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    const { useChatStore } = await import('@/lib/stores/useChatStore');
    const { useTaskStore } = await import('@/lib/stores/useTaskStore');
    const { applyRealtimeEvent } = await import(
      '@/lib/transports/applyRealtimeEvent'
    );
    const task = useTaskStore.getState().tasks[0];
    useTaskStore.setState({ tasks: [{ ...task, id: '88' }] });

    applyRealtimeEvent({
      event_id: 'edu-1',
      event_type: 'education_triggered',
      task_id: '88',
      session_id: 'SESS-88',
      occurred_at: '2026-08-19T10:00:00Z',
      payload: {
        material_id: 'EDU-ALLERGY',
        category: 'allergy',
        title: '药物过敏安全宣教',
        document_version: '1.0',
        original_content: '宣教原文',
        patient_content: '通俗说明',
        spoken_content: '播报内容',
        auto_play: true,
      },
    });
    expect(
      useChatStore.getState().educationCards['88'][0].originalContent
    ).toBe('宣教原文');

    applyRealtimeEvent({
      event_id: 'consent-1',
      event_type: 'consent_triggered',
      task_id: '88',
      session_id: 'SESS-88',
      occurred_at: '2026-08-19T10:01:00Z',
      payload: {
        form_id: 'FORM-1',
        form_type: 'surgery',
        title: '手术知情同意提醒',
        document_version: '1.0',
        full_text: '完整条款',
        clauses: [
          {
            id: 'C1',
            clause_code: 'RISK',
            clause_name: '风险说明',
            patient_content: '风险内容',
            importance_level: 'critical',
            mandatory_delivery: true,
            explicit_confirmation_required: true,
          },
        ],
      },
    });
    expect(
      useChatStore.getState().consentRequests['88'][0].clauses[0].clauseName
    ).toBe('风险说明');

    applyRealtimeEvent({
      event_id: 'handoff-1',
      event_type: 'handoff_requested',
      task_id: '88',
      session_id: 'SESS-88',
      occurred_at: '2026-08-19T10:02:00Z',
      payload: {
        request_id: 'NURSE-1',
        reason: '需要测量血压',
        requested_action: 'measure_blood_pressure',
        action_label: '测量血压',
        patient_name: '张三',
        bed_no: '08床',
        urgency: 'urgent',
      },
    });
    expect(useTaskStore.getState().tasks[0].handoffRequired).toBe(true);
    expect(useTaskStore.getState().tasks[0].handoffActionLabel).toBe(
      '测量血压'
    );
    expect(
      useChatStore.getState().nurseAssistanceRequests['NURSE-1'].patientName
    ).toBe('张三');
  });

  it('首问完成后把旧 pending 会话恢复为 active 并解除流式锁定', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    const { useChatStore } = await import('@/lib/stores/useChatStore');
    const { applyRealtimeEvent } = await import(
      '@/lib/transports/applyRealtimeEvent'
    );

    useChatStore.setState({
      sessions: {
        '109': {
          id: 'SESS-109',
          sessionNo: 'SESS-109',
          taskId: '109',
          patientId: '84',
          encounterId: '84',
          interactionType: 'assessment',
          channelType: 'text',
          sessionStatus: 'pending',
          currentCicareStage: 'connect',
          answeredQuestionCount: 0,
          totalQuestionCount: 6,
          messages: [],
        },
      },
      streamingTaskId: '109',
    });

    applyRealtimeEvent({
      event_id: 'opening-completed-1',
      event_type: 'assistant_message_completed',
      task_id: '109',
      session_id: 'SESS-109',
      message_id: 'MSG-AI-OPENING',
      occurred_at: '2026-08-19T11:46:11+08:00',
      payload: {
        content_text: '周阿姨您好，请告诉我现在最不舒服的地方。',
        turn_no: 1,
        is_final: true,
      },
    });

    expect(useChatStore.getState().sessions['109'].sessionStatus).toBe(
      'active'
    );
    expect(useChatStore.getState().streamingTaskId).toBeNull();
  });
});
