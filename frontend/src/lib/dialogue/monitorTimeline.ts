import type { DialogueHistoryItem } from '@/lib/dialogue/historyTimeline';

export type MonitorTimelineFilter = 'all' | 'ai' | 'patient' | 'tool';
export type MonitorTimelineSort = 'asc' | 'desc';

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function filterMonitorTimeline(
  items: DialogueHistoryItem[],
  filter: MonitorTimelineFilter
): DialogueHistoryItem[] {
  if (filter === 'all') return items;
  return items.filter((item) => {
    if (filter === 'ai') {
      return item.kind === 'message' && item.message.role === 'ai';
    }
    if (filter === 'patient') {
      return item.kind === 'message' && item.message.role === 'patient';
    }
    return (
      item.kind === 'education' ||
      item.kind === 'consent' ||
      (item.kind === 'event' && item.event.eventType === 'handoff')
    );
  });
}

export function sortMonitorTimeline(
  items: DialogueHistoryItem[],
  sort: MonitorTimelineSort
): DialogueHistoryItem[] {
  return [...items].sort((left, right) => {
    const difference = timestamp(left.occurredAt) - timestamp(right.occurredAt);
    return sort === 'asc' ? difference : -difference;
  });
}

export function formatConversationDuration(
  startedAt?: string,
  endedAt?: string,
  now = new Date()
): string {
  if (!startedAt) return '—';
  const start = Date.parse(startedAt);
  if (!Number.isFinite(start)) return '—';
  const end = endedAt ? Date.parse(endedAt) : now.getTime();
  if (!Number.isFinite(end) || end < start) return '00:00';
  const totalSeconds = Math.floor((end - start) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}
