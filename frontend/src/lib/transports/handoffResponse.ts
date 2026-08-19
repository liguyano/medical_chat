import type { SseEnvelope } from '@/lib/api/contracts';

export function toHandoffSseEnvelope(
  response: Record<string, unknown>,
  fallback: {
    taskId: string;
    sessionId?: string;
    eventType: 'handoff_requested' | 'handoff_resolved';
  }
): SseEnvelope {
  return {
    event_id: String(response.event_id ?? `${fallback.eventType}-${Date.now()}`),
    event_type: String(
      response.event_type ?? fallback.eventType
    ) as SseEnvelope['event_type'],
    task_id: String(response.task_id ?? fallback.taskId),
    session_id: String(response.session_id ?? fallback.sessionId ?? ''),
    message_id:
      response.message_id === undefined || response.message_id === null
        ? undefined
        : String(response.message_id),
    occurred_at: String(
      response.timestamp ??
        response.handled_at ??
        new Date().toISOString()
    ),
    payload: response,
  };
}
