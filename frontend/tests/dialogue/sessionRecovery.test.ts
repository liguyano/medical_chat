import { describe, expect, it } from 'vitest';
import {
  isDialogueSnapshotLoading,
  shouldEnableDialogueStream,
  shouldLoadDialogueSnapshot,
} from '@/lib/dialogue/sessionRecovery';

describe('患者对话会话恢复策略', () => {
  it('API 模式切换到尚未解析的新快照键时重新进入加载态', () => {
    expect(isDialogueSnapshotLoading('api', '3:SESSION-NEW', '3:SESSION-OLD')).toBe(
      true
    );
    expect(isDialogueSnapshotLoading('api', '3:SESSION-NEW', '3:SESSION-NEW')).toBe(
      false
    );
    expect(isDialogueSnapshotLoading('mock', '3:SESSION-NEW', null)).toBe(false);
  });

  it('只有快照已解析且存在会话时才订阅对话事件流', () => {
    expect(
      shouldEnableDialogueStream({
        hasTask: true,
        hasSession: false,
        readOnly: false,
        snapshotLoading: false,
      })
    ).toBe(false);
    expect(
      shouldEnableDialogueStream({
        hasTask: true,
        hasSession: true,
        readOnly: false,
        snapshotLoading: true,
      })
    ).toBe(false);
    expect(
      shouldEnableDialogueStream({
        hasTask: true,
        hasSession: true,
        readOnly: false,
        snapshotLoading: false,
      })
    ).toBe(true);
  });

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
