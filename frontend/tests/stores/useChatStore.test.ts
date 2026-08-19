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
});
