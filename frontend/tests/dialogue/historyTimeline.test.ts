import { describe, expect, it } from 'vitest';
import { buildDialogueHistoryTimeline } from '@/lib/dialogue/historyTimeline';

describe('对话历史时间轴', () => {
  it('按发生时间合并消息、宣教、知情同意和人工事件', () => {
    const timeline = buildDialogueHistoryTimeline({
      messages: [
        {
          id: 'm-2',
          messageNo: 'm-2',
          sessionId: 's-1',
          turnNo: 2,
          role: 'ai',
          cicareStage: 'ask',
          intentType: 'question',
          contentText: '请问您每天抽几支烟？',
          occurredAt: '2026-08-19T10:03:00Z',
        },
        {
          id: 'm-1',
          messageNo: 'm-1',
          sessionId: 's-1',
          turnNo: 1,
          role: 'patient',
          cicareStage: 'ask',
          intentType: 'answer',
          contentText: '我抽烟',
          occurredAt: '2026-08-19T10:00:00Z',
        },
      ],
      educationCards: [
        {
          id: 'edu-1',
          taskId: '1',
          materialId: 'material-1',
          category: 'tobacco',
          title: '戒烟宣教',
          documentVersion: '1.0',
          originalContent: '原文',
          patientContent: '通俗说明',
          spokenContent: '播报内容',
          priority: 'medium',
          requiresAcknowledgement: true,
          autoPlay: true,
          acknowledged: false,
          occurredAt: '2026-08-19T10:01:00Z',
        },
      ],
      consentRequests: [
        {
          id: 'consent-1',
          taskId: '1',
          formId: 'form-1',
          formType: 'education',
          title: '知情同意',
          documentVersion: '1.0',
          fullText: '全文',
          clauses: [],
          status: 'signed',
          requiresSignature: true,
          autoPlay: true,
          occurredAt: '2026-08-19T10:02:00Z',
        },
      ],
      events: [
        {
          id: 'handoff-1',
          taskId: '1',
          eventType: 'handoff',
          title: '呼叫护士',
          description: '需要协助',
          priority: 'high',
          handled: false,
          occurredAt: '2026-08-19T10:04:00Z',
        },
      ],
    });

    expect(timeline.map((item) => item.kind)).toEqual([
      'message',
      'education',
      'consent',
      'message',
      'event',
    ]);
  });

  it('跳过 education 摘要事件，避免与完整宣教卡片重复', () => {
    const timeline = buildDialogueHistoryTimeline({
      events: [
        {
          id: 'education-event',
          taskId: '1',
          eventType: 'education',
          title: '医学宣教',
          description: '摘要',
          priority: 'medium',
          handled: false,
          occurredAt: '2026-08-19T10:00:00Z',
        },
      ],
    });

    expect(timeline).toEqual([]);
  });
});
