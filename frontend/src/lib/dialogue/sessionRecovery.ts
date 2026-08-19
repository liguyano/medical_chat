import type { DataMode } from '@/lib/runtime/config';

interface DialogueSnapshotLoadInput {
  dataMode: DataMode;
  hasTask: boolean;
  hasSession: boolean;
  snapshotKey: string;
  loadedSnapshotKey: string | null;
}

export function buildDialogueSnapshotKey(
  taskId: string,
  sessionId?: string
): string {
  return `${taskId}:${sessionId ?? ''}`;
}

export function shouldLoadDialogueSnapshot({
  dataMode,
  hasTask,
  hasSession,
  snapshotKey,
  loadedSnapshotKey,
}: DialogueSnapshotLoadInput): boolean {
  if (!hasTask) return false;
  if (dataMode === 'mock') return !hasSession;
  return loadedSnapshotKey !== snapshotKey;
}
