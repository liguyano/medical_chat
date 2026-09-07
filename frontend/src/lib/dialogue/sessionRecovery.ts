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

export function isDialogueSnapshotLoading(
  dataMode: DataMode,
  snapshotKey: string,
  resolvedSnapshotKey: string | null
): boolean {
  return dataMode === 'api' && resolvedSnapshotKey !== snapshotKey;
}

interface DialogueStreamInput {
  hasTask: boolean;
  hasSession: boolean;
  readOnly: boolean;
  snapshotLoading: boolean;
}

export function shouldEnableDialogueStream({
  hasTask,
  hasSession,
  readOnly,
  snapshotLoading,
}: DialogueStreamInput): boolean {
  return hasTask && hasSession && !readOnly && !snapshotLoading;
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
