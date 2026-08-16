import { describe, expect, it } from 'vitest';
import { parseSseEnvelope } from '@/lib/transports/sseClient';

describe('SSE envelope parser', () => {
  it('解析统一事件信封', () => {
    const event = parseSseEnvelope(
      JSON.stringify({
        event_id: '1723-0',
        event_type: 'assistant_text_delta',
        task_id: 1,
        session_id: 2,
        message_id: 'MSG-1',
        occurred_at: '2026-08-16T10:00:00Z',
        payload: { delta: '您好' },
      })
    );
    expect(event.event_id).toBe('1723-0');
    expect(event.task_id).toBe('1');
    expect(event.session_id).toBe('2');
    expect(event.payload.delta).toBe('您好');
  });

  it('兼容旧版type/data结构和SSE id', () => {
    const event = parseSseEnvelope(
      JSON.stringify({
        type: 'progress_updated',
        task_id: 'T-1',
        data: { current: 3, total: 10 },
      }),
      'dialog_message',
      '1724-0'
    );
    expect(event.event_type).toBe('progress_updated');
    expect(event.event_id).toBe('1724-0');
    expect(event.payload.current).toBe(3);
  });
});
