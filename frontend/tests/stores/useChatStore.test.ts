import { afterEach, describe, expect, it, vi } from 'vitest';

describe('患者对话 Store', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('不把正在流式输出的任务编号持久化到下一次页面恢复', async () => {
    const values = new Map<string, string>();
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    const { useChatStore } = await import('@/lib/stores/useChatStore');

    useChatStore.getState().setStreaming('109');

    const persisted = JSON.parse(
      values.get('medical-evaluate-chat-storage') ?? '{}'
    ) as {
      state?: {
        streamingTaskId?: string | null;
      };
    };
    expect(persisted.state?.streamingTaskId ?? null).toBeNull();
  });

  it('加载旧版本持久化数据时清除残留的流式任务编号', async () => {
    const values = new Map<string, string>([
      [
        'medical-evaluate-chat-storage',
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

    const { useChatStore } = await import('@/lib/stores/useChatStore');

    expect(useChatStore.getState().streamingTaskId).toBeNull();
  });

  it('加载 API 快照前只清除当前任务的陈旧领域卡片', async () => {
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
    store.upsertEducationCard('112', card('112', 'OLD-STREAM-ID'));
    store.upsertEducationCard('113', card('113', 'DOMAIN-EVENT-2'));

    useChatStore.getState().clearTaskDomainState('112');

    expect(useChatStore.getState().educationCards['112']).toBeUndefined();
    expect(useChatStore.getState().educationCards['113']).toHaveLength(1);
  });
});
