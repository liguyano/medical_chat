import { describe, expect, it } from 'vitest';
import type { DialogueHistoryItem } from '@/lib/dialogue/historyTimeline';
import type { ConsentRequest, EducationCard } from '@/lib/types';
import {
  filterMonitorTimeline,
  formatConversationDuration,
  sortMonitorTimeline,
} from '@/lib/dialogue/monitorTimeline';

function message(
  id: string,
  role: 'ai' | 'patient',
  occurredAt: string
): DialogueHistoryItem {
  return {
    kind: 'message',
    id: `message-${id}`,
    occurredAt,
    message: {
      id,
      messageNo: id,
      sessionId: 'session-1',
      turnNo: 1,
      role,
      cicareStage: 'ask',
      intentType: role === 'ai' ? 'question' : 'answer',
      contentText: id,
      occurredAt,
    },
  };
}

const timeline: DialogueHistoryItem[] = [
  message('ai-1', 'ai', '2026-08-19T10:01:00Z'),
  message('patient-1', 'patient', '2026-08-19T10:02:00Z'),
  {
    kind: 'education',
    id: 'education-1',
    occurredAt: '2026-08-19T10:03:00Z',
    item: {
      id: 'education-1',
      taskId: 'task-1',
      materialId: 'material-1',
      category: 'general',
      title: '健康宣教',
      documentVersion: '1.0',
      originalContent: '原文',
      patientContent: '患者内容',
      spokenContent: '播报内容',
      priority: 'medium',
      requiresAcknowledgement: false,
      autoPlay: false,
      acknowledged: false,
      occurredAt: '2026-08-19T10:03:00Z',
    } satisfies EducationCard,
  },
  {
    kind: 'consent',
    id: 'consent-1',
    occurredAt: '2026-08-19T10:04:00Z',
    item: {
      id: 'consent-1',
      taskId: 'task-1',
      formId: 'form-1',
      formType: 'general',
      title: '知情同意书',
      documentVersion: '1.0',
      fullText: '同意内容',
      clauses: [],
      status: 'pending_signature',
      requiresSignature: true,
      autoPlay: false,
      occurredAt: '2026-08-19T10:04:00Z',
    } satisfies ConsentRequest,
  },
  {
    kind: 'event',
    id: 'event-1',
    occurredAt: '2026-08-19T10:05:00Z',
    event: {
      id: 'event-1',
      taskId: 'task-1',
      eventType: 'handoff',
      title: '呼叫护士',
      description: '需要协助',
      priority: 'high',
      handled: false,
      occurredAt: '2026-08-19T10:05:00Z',
    },
  },
];

describe('医护监控对话时间轴', () => {
  it('按消息类型筛选 AI、患者和工具结果', () => {
    expect(filterMonitorTimeline(timeline, 'ai').map((item) => item.id)).toEqual([
      'message-ai-1',
    ]);
    expect(filterMonitorTimeline(timeline, 'patient').map((item) => item.id)).toEqual([
      'message-patient-1',
    ]);
    expect(filterMonitorTimeline(timeline, 'tool').map((item) => item.id)).toEqual([
      'education-1',
      'consent-1',
      'event-1',
    ]);
    expect(filterMonitorTimeline(timeline, 'all')).toBe(timeline);
  });

  it('支持按发生时间正序和倒序排列', () => {
    const reversed = [...timeline].reverse();
    expect(sortMonitorTimeline(reversed, 'asc').map((item) => item.id)).toEqual(
      timeline.map((item) => item.id)
    );
    expect(sortMonitorTimeline(timeline, 'desc').map((item) => item.id)).toEqual(
      [...timeline].reverse().map((item) => item.id)
    );
  });

  it('格式化未结束、已结束和跨小时的对话时长', () => {
    const start = '2026-08-19T10:00:00Z';
    expect(
      formatConversationDuration(start, '2026-08-19T10:00:00Z')
    ).toBe('00:00');
    expect(
      formatConversationDuration(start, '2026-08-19T10:03:05Z')
    ).toBe('03:05');
    expect(
      formatConversationDuration(
        start,
        undefined,
        new Date('2026-08-19T11:02:03Z')
      )
    ).toBe('01:02:03');
    expect(formatConversationDuration()).toBe('—');
  });
});
