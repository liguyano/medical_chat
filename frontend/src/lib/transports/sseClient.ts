import type {
  SseEnvelope,
  SseEventType,
} from '@/lib/api/contracts';
import { runtimeConfig } from '@/lib/runtime/config';

export type StreamConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'closed'
  | 'error';

export interface SseClientOptions {
  path: string;
  onEvent: (event: SseEnvelope) => void;
  onStatusChange?: (status: StreamConnectionStatus) => void;
  onError?: (error: Error) => void;
  initialLastEventId?: string;
  maxReconnectDelayMs?: number;
}

const EVENT_TYPES: SseEventType[] = [
  'session_snapshot',
  'session_status',
  'user_transcript_delta',
  'user_transcript_completed',
  'assistant_message_started',
  'assistant_text_delta',
  'assistant_audio_delta',
  'assistant_message_completed',
  'extraction_updated',
  'progress_updated',
  'education_triggered',
  'education_status_updated',
  'consent_triggered',
  'handoff_requested',
  'handoff_resolved',
  'task_status_updated',
  'error',
  'heartbeat',
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {};
}

export function parseSseEnvelope(
  data: string,
  fallbackEventType?: string,
  fallbackEventId?: string
): SseEnvelope {
  const parsed = asRecord(JSON.parse(data));
  const payloadCandidate = parsed.payload ?? parsed.data;
  const eventType = String(
    parsed.event_type ??
      parsed.type ??
      fallbackEventType ??
      'heartbeat'
  ) as SseEventType;
  return {
    event_id: String(parsed.event_id ?? fallbackEventId ?? ''),
    event_type: eventType,
    task_id: String(parsed.task_id ?? ''),
    session_id:
      parsed.session_id === undefined
        ? undefined
        : String(parsed.session_id),
    message_id:
      parsed.message_id === undefined
        ? undefined
        : String(parsed.message_id),
    occurred_at: String(
      parsed.occurred_at ?? new Date().toISOString()
    ),
    payload:
      payloadCandidate && typeof payloadCandidate === 'object'
        ? (payloadCandidate as Record<string, unknown>)
        : parsed,
  };
}

function withLastEventId(path: string, lastEventId?: string): string {
  const url = new URL(path, runtimeConfig.apiBaseUrl);
  if (lastEventId) url.searchParams.set('last_event_id', lastEventId);
  return url.toString();
}

export class SseClient {
  private source?: EventSource;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private reconnectAttempts = 0;
  private manuallyClosed = false;
  private lastEventId?: string;
  private readonly processedEventIds = new Set<string>();

  constructor(private readonly options: SseClientOptions) {
    this.lastEventId = options.initialLastEventId;
  }

  connect(): void {
    if (typeof window === 'undefined' || this.source) return;
    this.manuallyClosed = false;
    this.options.onStatusChange?.(
      this.reconnectAttempts ? 'reconnecting' : 'connecting'
    );
    const source = new EventSource(
      withLastEventId(this.options.path, this.lastEventId),
      { withCredentials: true }
    );
    this.source = source;

    source.onopen = () => {
      this.reconnectAttempts = 0;
      this.options.onStatusChange?.('connected');
    };

    const handle = (event: MessageEvent, eventType?: string) => {
      try {
        const envelope = parseSseEnvelope(
          event.data,
          eventType,
          event.lastEventId
        );
        if (
          envelope.event_id &&
          this.processedEventIds.has(envelope.event_id)
        ) {
          return;
        }
        if (envelope.event_id) {
          this.lastEventId = envelope.event_id;
          this.processedEventIds.add(envelope.event_id);
          if (this.processedEventIds.size > 1000) {
            const oldest = this.processedEventIds.values().next().value;
            if (oldest) this.processedEventIds.delete(oldest);
          }
        }
        this.options.onEvent(envelope);
      } catch (error) {
        this.options.onError?.(
          error instanceof Error ? error : new Error('SSE事件解析失败')
        );
      }
    };

    source.onmessage = (event) => handle(event);
    for (const eventType of [
      ...EVENT_TYPES,
      'dialog_message',
      'monitor_message',
    ]) {
      source.addEventListener(eventType, (event) => {
        if (event instanceof MessageEvent) {
          handle(event, eventType);
        }
      });
    }

    source.onerror = () => {
      source.close();
      this.source = undefined;
      if (this.manuallyClosed) return;
      this.options.onStatusChange?.('reconnecting');
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts += 1;
    const maxDelay = this.options.maxReconnectDelayMs ?? 30_000;
    const baseDelay = Math.min(
      maxDelay,
      1000 * 2 ** Math.min(this.reconnectAttempts - 1, 5)
    );
    const jitter = Math.floor(Math.random() * 500);
    this.reconnectTimer = globalThis.setTimeout(
      () => this.connect(),
      baseDelay + jitter
    );
  }

  close(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer) globalThis.clearTimeout(this.reconnectTimer);
    this.source?.close();
    this.source = undefined;
    this.options.onStatusChange?.('closed');
  }
}

export function createDialogueSsePath(sessionId: string): string {
  return `/api/sse/dialog/${encodeURIComponent(sessionId)}`;
}

export function createMonitorSsePath(sessionId: string): string {
  return `/api/sse/monitor/${encodeURIComponent(sessionId)}`;
}
