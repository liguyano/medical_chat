import { createElement, type EffectCallback } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import PatientDialoguePage from '@/app/patient/dialogue/[taskId]/page';
import { careRepository } from '@/lib/repositories';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useChatStore } from '@/lib/stores/useChatStore';
import type { CareTask, InteractionSession } from '@/lib/types';

const hooks = vi.hoisted(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => { storage.set(key, value); },
    removeItem: (key: string) => { storage.delete(key); },
  });
  return { effects: [] as EffectCallback[] };
});

// 保留真实 React 渲染与 Zustand，只捕获 Effect 来重放开发模式的清理/再次加载顺序。
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    useEffect: (effect: EffectCallback) => { hooks.effects.push(effect); },
    useSyncExternalStore: (_subscribe: unknown, getSnapshot: () => unknown) => getSnapshot(),
  };
});
vi.mock('next/navigation', () => ({
  useParams: () => ({ taskId: '86' }),
  usePathname: () => '/patient/dialogue/86',
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));
vi.mock('@/hooks/useRealtimeStream', () => ({
  useRealtimeStream: () => ({ status: 'idle', error: '' }),
}));
vi.mock('@/lib/runtime/config', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/runtime/config')>(),
  runtimeConfig: { dataMode: 'api', apiBaseUrl: '', requestTimeoutMs: 15000 },
}));

const task: CareTask = {
  id: '86', taskNo: 'TEST-86', sessionId: 'SESSION-86',
  patientId: 'TEST-PATIENT', encounterId: 'TEST-ENCOUNTER',
  patientName: '测试患者', bedNo: 'TEST', taskType: '测试评估',
  collectionMode: 'ai_dialogue', taskStatus: 'in_progress',
  assignedNurseId: 'TEST-NURSE', assignedNurseName: '测试护士',
  createdAt: '2026-10-15T00:00:00Z',
};
const session: InteractionSession = {
  id: 'SESSION-86', sessionNo: 'SESSION-86', taskId: '86',
  patientId: task.patientId, encounterId: task.encounterId,
  interactionType: 'assessment', channelType: 'text',
  sessionStatus: 'active', currentCicareStage: 'connect', messages: [],
};

describe('患者对话页实际加载 Effect', () => {
  afterAll(() => vi.unstubAllGlobals());
  afterEach(() => {
    hooks.effects = [];
    useChatStore.getState().clearSession('86');
    useTaskStore.getState().setTasks([]);
  });

  it('清理首次请求后重跑页面 Effect，仍发起请求并恢复真实 Store 会话', async () => {
    useTaskStore.getState().setTasks([task]);
    const load = vi.spyOn(careRepository, 'getDialogueSnapshot').mockResolvedValue({
      session, answers: [], events: [], manualIntervention: false,
    });
    renderToStaticMarkup(createElement(PatientDialoguePage));
    const loadEffect = hooks.effects[0];
    const cleanupFirst = loadEffect();
    expect(load).toHaveBeenCalledTimes(1);
    if (typeof cleanupFirst !== 'function') throw new Error('首次加载应提供取消清理');
    cleanupFirst();
    expect(load.mock.calls[0][1]?.aborted).toBe(true);
    const cleanupSecond = loadEffect();
    expect(load).toHaveBeenCalledTimes(2);
    expect(load.mock.calls[1][1]?.aborted).toBe(false);
    await vi.waitFor(() => expect(useChatStore.getState().sessions['86']?.id).toBe('SESSION-86'));
    if (typeof cleanupSecond === 'function') cleanupSecond();
  });
});
