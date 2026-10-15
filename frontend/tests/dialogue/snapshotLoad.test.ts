import { describe, expect, it, vi } from 'vitest';
import { startDialogueSnapshotLoad } from '@/lib/dialogue/snapshotLoad';
import { shouldLoadDialogueSnapshot } from '@/lib/dialogue/sessionRecovery';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('患者会话快照加载生命周期', () => {
  it('首次加载被取消后重新进入能完成加载，不写入旧响应', async () => {
    const first = deferred<string>();
    let firstSignal: AbortSignal | undefined;
    let loadedKey: string | null = null;
    let displayedSession: string | null = null;
    const onSuccess = (session: string) => {
      loadedKey = '86:SESSION-86';
      displayedSession = session;
    };
    const cancel = startDialogueSnapshotLoad({
      load: (signal) => { firstSignal = signal; return first.promise; },
      onSuccess,
      onError: (error) => { throw error; },
    });
    cancel();
    expect(firstSignal?.aborted).toBe(true);
    expect(shouldLoadDialogueSnapshot({
      dataMode: 'api', hasTask: true, hasSession: false,
      snapshotKey: '86:SESSION-86', loadedSnapshotKey: loadedKey,
    })).toBe(true);
    const cleanup = startDialogueSnapshotLoad({
      load: async () => '最新会话', onSuccess,
      onError: (error) => { throw error; },
    });
    await vi.waitFor(() => expect(displayedSession).toBe('最新会话'));
    first.resolve('已取消的旧会话');
    await first.promise;
    await Promise.resolve();
    expect(displayedSession).toBe('最新会话');
    expect(loadedKey).toBe('86:SESSION-86');
    cleanup();
  });

  it('取消后的迟到失败不覆盖当前页面错误状态', async () => {
    const request = deferred<string>();
    const onError = vi.fn();
    const cancel = startDialogueSnapshotLoad({
      load: () => request.promise, onSuccess: vi.fn(), onError,
    });
    cancel();
    request.reject(new Error('旧请求失败'));
    await request.promise.catch(() => undefined);
    await Promise.resolve();
    expect(onError).not.toHaveBeenCalled();
  });

  it('真实失败会展示错误，随后重试可以成功', async () => {
    let errorMessage = '';
    let session = '';
    const onSuccess = (value: string) => { session = value; errorMessage = ''; };
    const onError = (error: unknown) => { errorMessage = (error as Error).message; };
    const cleanupFirst = startDialogueSnapshotLoad({
      load: async () => { throw new Error('网络超时'); }, onSuccess, onError,
    });
    await vi.waitFor(() => expect(errorMessage).toBe('网络超时'));
    cleanupFirst();
    const cleanupRetry = startDialogueSnapshotLoad({
      load: async () => '恢复后的会话', onSuccess, onError,
    });
    await vi.waitFor(() => expect(session).toBe('恢复后的会话'));
    expect(errorMessage).toBe('');
    cleanupRetry();
  });
});
