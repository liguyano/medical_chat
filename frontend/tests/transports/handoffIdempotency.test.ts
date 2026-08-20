import { afterEach, describe, expect, it, vi } from 'vitest';

describe('handoff event identity', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('HTTP 与 SSE 的同一业务事件只保留一个组件，不同事件仍全部保留', async () => {
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
      events: {},
      nurseAssistanceRequests: {},
    });

    const first = {
      event_id: 'HANDOFF-EVENT-1',
      event_type: 'handoff_requested' as const,
      task_id: '109',
      session_id: 'SESS-109',
      occurred_at: '2026-08-20T10:00:00Z',
      payload: {
        request_id: 'NURSE-1',
        request_source: 'patient',
        reason: '患者主动请求护士协助',
        requested_action: 'other',
        action_label: '人工护理协助',
        status: 'requested',
      },
    };
    applyRealtimeEvent(first);
    applyRealtimeEvent(first);
    applyRealtimeEvent({
      ...first,
      event_id: 'HANDOFF-EVENT-2',
      occurred_at: '2026-08-20T10:00:01Z',
      payload: {
        ...first.payload,
        request_id: 'NURSE-2',
      },
    });

    expect(useChatStore.getState().events['109']).toHaveLength(2);
    expect(
      Object.keys(useChatStore.getState().nurseAssistanceRequests)
    ).toEqual(['NURSE-1', 'NURSE-2']);
  });
});
