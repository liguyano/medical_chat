import { afterEach, describe, expect, it, vi } from 'vitest';

describe('患者对话 Store', () => {
  afterEach(() => {
    vi.resetModules();
    vi.doUnmock('@/lib/runtime/config');
    vi.unstubAllGlobals();
  });

  it('API 模式不暴露与真实任务编号冲突的 Mock 患者会话', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    vi.doMock('@/lib/runtime/config', () => ({
      runtimeConfig: {
        dataMode: 'api',
        apiBaseUrl: 'http://localhost:8000',
        dialogTransport: 'websocket',
        requestTimeoutMs: 15_000,
      },
    }));

    const { useChatStore } = await import('@/lib/stores/useChatStore');

    expect(useChatStore.getState().sessions).toEqual({});
    expect(useChatStore.getState().structuredAnswers).toEqual({});
    expect(useChatStore.getState().events).toEqual({});
  });

  it('API 模式不恢复旧通用存储键中的 Mock 完成会话', async () => {
    const values = new Map<string, string>([
      [
        'medical-evaluate-chat-storage',
        JSON.stringify({
          state: {
            sessions: {
              '3': {
                id: 'SESSION-3',
                taskId: '3',
                patientId: '3',
                sessionStatus: 'completed',
                answeredQuestionCount: 15,
                totalQuestionCount: 15,
                messages: [],
              },
            },
          },
          version: 0,
        }),
      ],
    ]);
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    vi.doMock('@/lib/runtime/config', () => ({
      runtimeConfig: {
        dataMode: 'api',
        apiBaseUrl: 'http://localhost:8000',
        dialogTransport: 'websocket',
        requestTimeoutMs: 15_000,
      },
    }));

    const { useChatStore } = await import('@/lib/stores/useChatStore');

    expect(useChatStore.getState().sessions).toEqual({});
  });

  it('不把正在流式输出的任务编号持久化到下一次页面恢复', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    vi.doMock('@/lib/runtime/config', () => ({
      runtimeConfig: {
        dataMode: 'api',
        apiBaseUrl: 'http://localhost:8000',
        dialogTransport: 'websocket',
        requestTimeoutMs: 15_000,
      },
    }));
    const { useChatStore } = await import('@/lib/stores/useChatStore');

    useChatStore.getState().setStreaming('109');

    const rawPersisted = values.get('medical-evaluate-chat-storage-api');
    expect(rawPersisted).toBeDefined();
    const persisted = JSON.parse(rawPersisted ?? '{}') as {
      state?: {
        streamingTaskId?: string | null;
      };
    };
    expect(persisted.state?.streamingTaskId ?? null).toBeNull();
  });

  it('加载旧版本持久化数据时清除残留的流式任务编号', async () => {
    const values = new Map<string, string>([
      [
        'medical-evaluate-chat-storage-api',
        JSON.stringify({
          state: {
            sessions: {},
            structuredAnswers: {},
            events: {},
            educationCards: {},
            consentRequests: {},
            nurseAssistanceRequests: {},
            feedback: {},
            streamingTaskId: '109',
          },
          version: 0,
        }),
      ],
    ]);
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    vi.doMock('@/lib/runtime/config', () => ({
      runtimeConfig: {
        dataMode: 'api',
        apiBaseUrl: 'http://localhost:8000',
        dialogTransport: 'websocket',
        requestTimeoutMs: 15_000,
      },
    }));

    const { useChatStore } = await import('@/lib/stores/useChatStore');

    expect(useChatStore.getState().streamingTaskId).toBeNull();
  });

  it('加载 API 快照前清除当前任务的全部陈旧会话和领域状态', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    const { useChatStore } = await import('@/lib/stores/useChatStore');
    const store = useChatStore.getState();
    const card = (taskId: string, id: string) => ({
      id,
      taskId,
      materialId: `MATERIAL-${id}`,
      category: 'tobacco',
      title: '戒烟宣教',
      documentVersion: '1.0',
      originalContent: '原文',
      patientContent: '通俗文本',
      spokenContent: '播报文本',
      priority: 'medium' as const,
      requiresAcknowledgement: true,
      autoPlay: true,
      acknowledged: false,
      occurredAt: '2026-08-20T10:00:00Z',
    });
    useChatStore.setState({
      sessions: {
        '112': { taskId: '112', messages: [] } as never,
        '113': { taskId: '113', messages: [] } as never,
      },
      structuredAnswers: { '112': [], '113': [] },
      events: { '112': [], '113': [] },
      consentRequests: { '112': [], '113': [] },
      nurseAssistanceRequests: {
        'REQUEST-112': { taskId: '112' } as never,
        'REQUEST-113': { taskId: '113' } as never,
      },
      feedback: {
        'MESSAGE-112': { taskId: '112' } as never,
        'MESSAGE-113': { taskId: '113' } as never,
      },
    });
    store.upsertEducationCard('112', card('112', 'OLD-STREAM-ID'));
    store.upsertEducationCard('113', card('113', 'DOMAIN-EVENT-2'));

    useChatStore.getState().clearSession('112');

    const state = useChatStore.getState();
    expect(state.sessions['112']).toBeUndefined();
    expect(state.structuredAnswers['112']).toBeUndefined();
    expect(state.events['112']).toBeUndefined();
    expect(state.educationCards['112']).toBeUndefined();
    expect(state.consentRequests['112']).toBeUndefined();
    expect(state.nurseAssistanceRequests['REQUEST-112']).toBeUndefined();
    expect(state.feedback['MESSAGE-112']).toBeUndefined();
    expect(state.sessions['113']).toBeDefined();
    expect(state.educationCards['113']).toHaveLength(1);
    expect(state.nurseAssistanceRequests['REQUEST-113']).toBeDefined();
    expect(state.feedback['MESSAGE-113']).toBeDefined();
  });
});
