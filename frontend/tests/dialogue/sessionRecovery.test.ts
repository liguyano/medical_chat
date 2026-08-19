import { describe, expect, it } from 'vitest';
import { shouldLoadDialogueSnapshot } from '@/lib/dialogue/sessionRecovery';

describe('患者对话会话恢复策略', () => {
  it('API 模式即使已有持久化会话，也必须刷新后端快照', () => {
    expect(
      shouldLoadDialogueSnapshot({
        dataMode: 'api',
        hasTask: true,
        hasSession: true,
        snapshotKey: '109:SESS-109',
        loadedSnapshotKey: null,
      })
    ).toBe(true);
  });

  it('同一个任务快照已经加载后不重复请求', () => {
    expect(
      shouldLoadDialogueSnapshot({
        dataMode: 'api',
        hasTask: true,
        hasSession: true,
        snapshotKey: '109:SESS-109',
        loadedSnapshotKey: '109:SESS-109',
      })
    ).toBe(false);
  });

  it('Mock 模式保留已有会话，不请求后端快照', () => {
    expect(
      shouldLoadDialogueSnapshot({
        dataMode: 'mock',
        hasTask: true,
        hasSession: true,
        snapshotKey: '109:SESS-109',
        loadedSnapshotKey: null,
      })
    ).toBe(false);
  });
});
