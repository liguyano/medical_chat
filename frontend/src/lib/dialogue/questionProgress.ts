import type { CareRepository } from '@/lib/repositories/types';
import type { QuestionProgress } from '@/lib/types/questionProgress';

export interface QuestionProgressState {
  data: QuestionProgress | null;
  error: string | null;
}

/** 每个会话独立资源；请求序号与取消信号共同阻止迟到响应回写。 */
export function createQuestionProgressResource(
  repository: Pick<CareRepository, 'getQuestionProgress'>,
  sessionId: string | undefined
) {
  let state: QuestionProgressState = { data: null, error: null };
  let revision = 0;
  let pending = false;
  let controller: AbortController | undefined;
  const listeners = new Set<() => void>();
  const publish = (next: QuestionProgressState) => {
    state = next;
    listeners.forEach((listener) => listener());
  };
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    cancel() {
      revision += 1;
      pending = false;
      controller?.abort();
    },
    async refresh(skipIfPending = false) {
      if (!sessionId || (skipIfPending && pending)) return;
      pending = true;
      const requestRevision = ++revision;
      controller?.abort();
      controller = new AbortController();
      try {
        const data = await repository.getQuestionProgress(sessionId, controller.signal);
        if (requestRevision !== revision) return;
        if (data.sessionId !== sessionId) throw new Error('Unexpected session');
        publish({ data, error: null });
      } catch {
        if (requestRevision !== revision) return;
        publish({ data: state.data, error: '进度暂时无法更新，请稍后重试。' });
      } finally {
        if (requestRevision === revision) pending = false;
      }
    },
  };
}
