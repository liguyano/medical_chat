import { afterEach, describe, expect, it, vi } from 'vitest';

describe('患者任务 Store', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('API 模式不暴露与后端任务编号冲突的 Mock 任务', async () => {
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

    const { useTaskStore } = await import('@/lib/stores/useTaskStore');

    expect(useTaskStore.getState().tasks).toEqual([]);
  });

  it('API 模式重置 Store 后仍不注入 Mock 任务', async () => {
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
    const { useTaskStore } = await import('@/lib/stores/useTaskStore');
    useTaskStore.setState({ tasks: [] });

    useTaskStore.getState().resetDemoData();

    expect(useTaskStore.getState().tasks).toEqual([]);
  });
});
