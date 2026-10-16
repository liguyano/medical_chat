import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import NurseReviewPage from '@/app/nurse/tasks/[id]/review/page';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useChatStore } from '@/lib/stores/useChatStore';
import type { CareTask } from '@/lib/types';

vi.hoisted(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal('sessionStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => { storage.set(key, value); },
    removeItem: (key: string) => { storage.delete(key); },
  });
});
// Node 服务端渲染默认读取 Zustand 的初始快照；此处只替换订阅绑定，读写仍用真实 Store。
vi.mock('@/lib/stores/useTaskStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/stores/useTaskStore')>();
  return { useTaskStore: Object.assign(
    (selector: (state: ReturnType<typeof actual.useTaskStore.getState>) => unknown) => selector(actual.useTaskStore.getState()),
    actual.useTaskStore,
  ) };
});
vi.mock('@/lib/stores/useChatStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/stores/useChatStore')>();
  return { useChatStore: Object.assign(
    (selector: (state: ReturnType<typeof actual.useChatStore.getState>) => unknown) => selector(actual.useChatStore.getState()),
    actual.useChatStore,
  ) };
});
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: '87' }), useRouter: () => ({ push: vi.fn() }),
}));
// 隔离登录边界；题目、输入、差异计数及原因框均由真实复核页面渲染。
vi.mock('@/components/layout/NurseLayout', () => ({
  default: ({ children }: { children: ReactNode }) => createElement('main', null, children),
}));

const task: CareTask = {
  id: '87', taskNo: 'TEST-87', patientId: 'TEST-PATIENT', encounterId: 'TEST-ENCOUNTER',
  patientName: '测试患者', bedNo: 'TEST', taskType: '测试评估',
  collectionMode: 'ai_dialogue', taskStatus: 'pending_review',
  assignedNurseId: 'TEST-NURSE', assignedNurseName: '测试护士', createdAt: '2026-10-16T00:00:00Z',
};

describe('护士复核页面逐题差异', () => {
  afterAll(() => vi.unstubAllGlobals());
  afterEach(() => {
    useTaskStore.setState({ tasks: [], reviews: {} });
    useChatStore.getState().clearSession('87');
  });

  it('部分护士草稿不清空其他题，只有修改题显示原因输入', () => {
    useTaskStore.getState().setTasks([task]);
    useChatStore.getState().setStructuredAnswers('87', [
      { questionId: 'q1', questionCode: 'Q1', questionText: '进食情况', answerText: '全部自理', sourceMessageIds: [], extractionConfidence: 1, corrected: false },
      { questionId: 'q2', questionCode: 'Q2', questionText: '洗澡情况', answerText: '能自理', sourceMessageIds: [], extractionConfidence: 1, corrected: false },
    ]);
    useTaskStore.getState().saveReview({
      taskId: '87', nurseAnswers: { q1: '需协助' }, finalAnswers: {},
      correctionReasons: {}, status: 'draft',
    });
    const html = renderToStaticMarkup(createElement(NurseReviewPage));
    expect(html).toContain('value="能自理"');
    expect(html).toContain('1项差异');
    expect(html).toContain('修改原因（必填）');
    expect(html).toContain('进食情况的修改原因');
    expect(html).not.toContain('洗澡情况的修改原因');
  });
});
