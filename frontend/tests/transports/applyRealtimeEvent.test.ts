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
});
