import { afterEach, describe, expect, it, vi } from 'vitest';

describe('用户会话 Store', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('完成 sessionStorage 恢复后才标记 hasHydrated', async () => {
    const values = new Map<string, string>([
      [
        'user-storage',
        JSON.stringify({
          state: {
            user: {
              id: 'P001',
              role: 'patient',
              name: '测试患者',
              department: '心内科',
            },
            isAuthenticated: true,
          },
          version: 0,
        }),
      ],
    ]);
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    };
    vi.stubGlobal('sessionStorage', storage);

    const { useUserStore } = await import('@/lib/stores/useUserStore');
    const state = useUserStore.getState();

    expect(state.hasHydrated).toBe(true);
    expect(state.user).toMatchObject({
      id: 'P001',
      role: 'patient',
      name: '测试患者',
    });
    expect(state.isAuthenticated).toBe(true);
  });
});
