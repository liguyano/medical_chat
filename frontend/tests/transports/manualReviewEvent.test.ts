import { afterEach, describe, expect, it, vi } from 'vitest';

describe('固定人工审核实时事件', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('系统固定人工审核不会被前端误标为患者正在呼叫医护', async () => {
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

    useTaskStore.setState({
      tasks: [
        {
          id: '88',
          taskNo: 'TASK-88',
          sessionId: 'SESS-88',
          patientId: '1',
          encounterId: '1',
          patientName: '测试患者',
          bedNo: '08',
          taskType: '入院评估任务包',
          collectionMode: 'ai_dialogue',
          taskStatus: 'in_progress',
          assignedNurseId: '1',
          assignedNurseName: '责任护士',
          createdAt: '2026-09-10T08:00:00Z',
        },
      ],
    });
    useChatStore.setState({ nurseAssistanceRequests: {}, events: {} });

    applyRealtimeEvent({
      event_id: 'MANUAL-REVIEW-EVENT-88',
      event_type: 'handoff_requested',
      task_id: '88',
      session_id: 'SESS-88',
      occurred_at: '2026-09-10T08:10:00Z',
      payload: {
        request_id: 'MANUAL-REVIEW-88',
        request_source: 'system',
        requested_action: 'planned_manual_review',
        action_label: '固定条目人工审核（2项）',
        title: '固定条目待人工审核',
        reason: 'AI问答已完成，剩余2项固定条目需要护士人工审核',
        status: 'requested',
        urgency: 'routine',
        priority: 'medium',
        review_items: [
          {
            question_id: 21,
            question_code: 'outdoor_night_lighting',
            question_text: '夜间路灯和楼道照明良好',
          },
          {
            question_id: 22,
            question_code: 'indoor_stair_handrails',
            question_text: '室内楼梯均有可用扶手',
          },
        ],
      },
    });

    const task = useTaskStore.getState().tasks[0];
    expect(task.handoffRequired).not.toBe(true);
    expect(
      Object.keys(useChatStore.getState().nurseAssistanceRequests)
    ).toHaveLength(0);
    expect(useChatStore.getState().events['88']?.[0]?.title).toBe(
      '固定条目待人工审核'
    );
    expect(useChatStore.getState().events['88']?.[0]?.metadata?.requestSource).toBe(
      'system'
    );
  });

  it('实时抽取保留固定人工审核 collection_status', async () => {
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
    useChatStore.setState({ structuredAnswers: {} });

    applyRealtimeEvent({
      event_id: 'extract-manual-1',
      event_type: 'extraction_updated',
      task_id: '88',
      session_id: 'SESS-88',
      occurred_at: '2026-09-10T08:11:00Z',
      payload: {
        fields: [
          {
            question_id: 21,
            question_code: 'outdoor_night_lighting',
            question_text: '夜间路灯和楼道照明良好',
            answer_type: 'boolean',
            display_value: '待护士人工审核',
            source_message_ids: [],
            confidence: 0,
            corrected: false,
            collection_status: 'manual_review_pending',
          },
        ],
      },
    });

    const answer = useChatStore.getState().structuredAnswers['88'][0];
    expect(answer.collectionStatus).toBe('manual_review_pending');
  });
});
