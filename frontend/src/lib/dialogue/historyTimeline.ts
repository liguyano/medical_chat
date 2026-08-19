import type {
  ConsentRequest,
  EducationCard,
  InteractionEvent,
  InteractionMessage,
} from '@/lib/types';

export type DialogueHistoryItem =
  | {
      kind: 'message';
      id: string;
      occurredAt: string;
      message: InteractionMessage;
    }
  | {
      kind: 'education';
      id: string;
      occurredAt: string;
      item: EducationCard;
    }
  | {
      kind: 'consent';
      id: string;
      occurredAt: string;
      item: ConsentRequest;
    }
  | {
      kind: 'event';
      id: string;
      occurredAt: string;
      event: InteractionEvent;
    };

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER;
}

/**
 * 将对话消息和工具领域对象合并成单一历史时间轴。
 * 组件的 occurredAt 来自后端事件快照，不能按 Store 分组后再渲染，
 * 否则所有工具卡片都会被推到对话末尾。
 */
export function buildDialogueHistoryTimeline(input: {
  messages?: InteractionMessage[];
  educationCards?: EducationCard[];
  consentRequests?: ConsentRequest[];
  events?: InteractionEvent[];
}): DialogueHistoryItem[] {
  const items: Array<DialogueHistoryItem & { sequence: number }> = [];
  let sequence = 0;

  for (const message of input.messages ?? []) {
    items.push({
      kind: 'message',
      id: `message-${message.id}`,
      occurredAt: message.occurredAt,
      message,
      sequence: sequence++,
    });
  }
  for (const item of input.educationCards ?? []) {
    items.push({
      kind: 'education',
      id: `education-${item.id}`,
      occurredAt: item.occurredAt,
      item,
      sequence: sequence++,
    });
  }
  for (const item of input.consentRequests ?? []) {
    items.push({
      kind: 'consent',
      id: `consent-${item.id}`,
      occurredAt: item.occurredAt,
      item,
      sequence: sequence++,
    });
  }
  for (const event of input.events ?? []) {
    // education 事件对应 educationCards，避免在时间轴重复显示一张摘要卡。
    if (event.eventType === 'education') continue;
    items.push({
      kind: 'event',
      id: `event-${event.id}`,
      occurredAt: event.occurredAt,
      event,
      sequence: sequence++,
    });
  }

  return items.sort(
    (left, right) =>
      timestamp(left.occurredAt) - timestamp(right.occurredAt) ||
      left.sequence - right.sequence
  );
}
