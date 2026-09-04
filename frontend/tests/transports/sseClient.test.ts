import { describe, expect, it } from 'vitest';
import {
  parseSseEnvelope,
  resolveTransportEventId,
} from '@/lib/transports/sseClient';

describe('SSE envelope parser', () => {
  it('解析统一事件信封', () => {
    const event = parseSseEnvelope(
      JSON.stringify({
        event_id: 'DOMAIN-EVENT-1',
        stream_id: '1723-0',
        event_type: 'assistant_text_delta',
        task_id: 1,
        session_id: 2,
        message_id: 'MSG-1',
        occurred_at: '2026-08-16T10:00:00Z',
        payload: { delta: '您好' },
      })
    );
    expect(event.event_id).toBe('DOMAIN-EVENT-1');
    expect(event.stream_id).toBe('1723-0');
    expect(event.task_id).toBe('1');
    expect(event.session_id).toBe('2');
    expect(event.payload.delta).toBe('您好');
  });

  it('业务 event_id 不得冒充断线续读游标', () => {
    const envelope = parseSseEnvelope(
      JSON.stringify({
        event_id: 'snapshot:GEN-1',
        event_type: 'assistant_text_delta',
        task_id: '1',
        payload: { snapshot: true, delta: '处理中' },
      })
    );

    expect(resolveTransportEventId(envelope, '')).toBeUndefined();
    expect(resolveTransportEventId(envelope, '1787205471545-0')).toBe(
      '1787205471545-0'
    );
  });

  it('优先使用 envelope stream_id 作为断线续读游标', () => {
    const envelope = parseSseEnvelope(
      JSON.stringify({
        event_id: 'snapshot:GEN-1',
        stream_id: '1787205471545-1',
        event_type: 'assistant_text_delta',
        task_id: '1',
        payload: { snapshot: true, delta: '处理中' },
      })
    );

    expect(resolveTransportEventId(envelope, '1787205471545-0')).toBe(
      '1787205471545-1'
    );
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
    expect(event.stream_id).toBe('1724-0');
    expect(event.payload.current).toBe(3);
  });
});
