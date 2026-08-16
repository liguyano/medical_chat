import type { SseEnvelope } from '@/lib/api/contracts';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type {
  InteractionEvent,
  InteractionMessage,
  InteractionSession,
  StructuredAnswer,
} from '@/lib/types';

function value<T>(payload: Record<string, unknown>, key: string, fallback: T): T {
  return (payload[key] as T | undefined) ?? fallback;
}

function currentSession(taskId: string): InteractionSession | undefined {
  return useChatStore.getState().sessions[taskId];
}

function ensureSession(event: SseEnvelope): InteractionSession {
  const existing = currentSession(event.task_id);
  if (existing) return existing;
  const sessionId = event.session_id ?? `SESSION-${event.task_id}`;
  const task = useTaskStore
    .getState()
    .tasks.find((item) => item.id === event.task_id);
  return {
    id: sessionId,
    sessionNo: sessionId,
    taskId: event.task_id,
    patientId: task?.patientId ?? '',
    encounterId: task?.encounterId ?? '',
    interactionType: 'assessment',
    channelType: 'mixed',
    sessionStatus: 'active',
    currentCicareStage: task?.currentStage ?? 'connect',
    messages: [],
  };
}

function buildMessage(
  event: SseEnvelope,
  role: InteractionMessage['role'],
  streaming: boolean
): InteractionMessage {
  const payload = event.payload;
  const messageId =
    event.message_id ??
    (payload.client_message_id === undefined
      ? undefined
      : String(payload.client_message_id)) ??
    value(payload, 'message_id', `MSG-${event.event_id || Date.now()}`);
  const session = ensureSession(event);
  return {
    id: messageId,
    messageNo: messageId,
    sessionId: event.session_id ?? session.id,
    turnNo: value(payload, 'turn_no', session.messages.length + 1),
    role,
    cicareStage: value(
      payload,
      'cicare_stage',
      session.currentCicareStage
    ) as InteractionMessage['cicareStage'],
    intentType: value(
      payload,
      'intent_type',
      role === 'ai' ? 'question' : 'answer'
    ) as InteractionMessage['intentType'],
    contentText: value(payload, 'content_text', value(payload, 'text', '')),
    occurredAt: event.occurred_at,
    isStreaming: streaming,
  };
}

function appendDelta(event: SseEnvelope, role: InteractionMessage['role']) {
  const store = useChatStore.getState();
  const session = ensureSession(event);
  if (!currentSession(event.task_id)) store.setSession(event.task_id, session);
  const message = buildMessage(event, role, true);
  const existing = currentSession(event.task_id)?.messages.find(
    (item) => item.id === message.id
  );
  const delta = value(event.payload, 'delta', value(event.payload, 'text', ''));
  store.upsertMessage(event.task_id, {
    ...message,
    contentText: `${existing?.contentText ?? ''}${delta}`,
  });
  if (role === 'ai') store.setStreaming(event.task_id);
}

export function applyRealtimeEvent(event: SseEnvelope): void {
  if (!event.task_id && event.event_type !== 'heartbeat') return;
  const chatStore = useChatStore.getState();
  const taskStore = useTaskStore.getState();
  const session = ensureSession(event);

  switch (event.event_type) {
    case 'session_snapshot': {
      chatStore.setSession(event.task_id, {
        ...session,
        sessionStatus: value(
          event.payload,
          'session_status',
          session.sessionStatus
        ) as InteractionSession['sessionStatus'],
        currentCicareStage: value(
          event.payload,
          'current_cicare_stage',
          session.currentCicareStage
        ) as InteractionSession['currentCicareStage'],
        answeredQuestionCount: value(
          event.payload,
          'answered_question_count',
          session.answeredQuestionCount
        ),
        totalQuestionCount: value(
          event.payload,
          'total_question_count',
          session.totalQuestionCount
        ),
        aiSummary: value(event.payload, 'ai_summary', session.aiSummary),
      });
      break;
    }
    case 'session_status': {
      chatStore.setSession(event.task_id, {
        ...session,
        sessionStatus: value(
          event.payload,
          'status',
          session.sessionStatus
        ) as InteractionSession['sessionStatus'],
      });
      break;
    }
    case 'user_transcript_delta':
      appendDelta(event, 'patient');
      break;
    case 'user_transcript_completed': {
      const message = buildMessage(event, 'patient', false);
      chatStore.upsertMessage(event.task_id, message);
      break;
    }
    case 'assistant_message_started': {
      if (!currentSession(event.task_id)) {
        chatStore.setSession(event.task_id, session);
      }
      chatStore.upsertMessage(
        event.task_id,
        buildMessage(event, 'ai', true)
      );
      chatStore.setStreaming(event.task_id);
      break;
    }
    case 'assistant_text_delta':
      appendDelta(event, 'ai');
      break;
    case 'assistant_message_completed': {
      const message = buildMessage(event, 'ai', false);
      const existing = currentSession(event.task_id)?.messages.find(
        (item) => item.id === message.id
      );
      chatStore.upsertMessage(event.task_id, {
        ...message,
        contentText: message.contentText || existing?.contentText || '',
        isStreaming: false,
      });
      chatStore.setStreaming(null);
      break;
    }
    case 'extraction_updated': {
      const raw =
        (event.payload.field as Record<string, unknown> | undefined) ??
        event.payload;
      const answer: StructuredAnswer = {
        questionId: String(raw.question_id ?? raw.field_id ?? ''),
        questionCode: String(raw.question_code ?? ''),
        questionText: String(raw.question_text ?? raw.field_name ?? '评估字段'),
        answerText:
          raw.answer_text === undefined ? undefined : String(raw.answer_text),
        answerNumber:
          typeof raw.answer_number === 'number'
            ? raw.answer_number
            : undefined,
        answerBoolean:
          typeof raw.answer_boolean === 'boolean'
            ? raw.answer_boolean
            : undefined,
        selectedOptions: Array.isArray(raw.selected_options)
          ? raw.selected_options.map(String)
          : undefined,
        sourceMessageIds: Array.isArray(raw.source_message_ids)
          ? raw.source_message_ids.map(String)
          : event.message_id
            ? [event.message_id]
            : [],
        extractionConfidence:
          typeof raw.confidence === 'number' ? raw.confidence : 0,
        corrected: Boolean(raw.corrected),
      };
      if (answer.questionId) chatStore.upsertStructuredAnswer(event.task_id, answer);
      break;
    }
    case 'progress_updated': {
      const current = value(event.payload, 'current', 0);
      const total = value(event.payload, 'total', 0);
      taskStore.updateTaskProgress(event.task_id, current, total);
      chatStore.setSession(event.task_id, {
        ...session,
        answeredQuestionCount: current,
        totalQuestionCount: total,
        currentCicareStage: value(
          event.payload,
          'cicare_stage',
          session.currentCicareStage
        ) as InteractionSession['currentCicareStage'],
      });
      break;
    }
    case 'education_triggered':
    case 'consent_triggered':
    case 'handoff_requested': {
      const eventType: InteractionEvent['eventType'] =
        event.event_type === 'education_triggered'
          ? 'education'
          : event.event_type === 'handoff_requested'
            ? 'handoff'
            : 'follow_up';
      chatStore.addEvent(event.task_id, {
        id: event.event_id || `EVENT-${Date.now()}`,
        taskId: event.task_id,
        messageId: event.message_id,
        eventType,
        title: value(
          event.payload,
          'title',
          eventType === 'handoff' ? '请求护士协助' : '护理提醒'
        ),
        description: value(event.payload, 'description', ''),
        priority: value(
          event.payload,
          'priority',
          eventType === 'handoff' ? 'high' : 'medium'
        ) as InteractionEvent['priority'],
        handled: false,
        occurredAt: event.occurred_at,
      });
      if (eventType === 'handoff') {
        taskStore.requestHandoff(
          event.task_id,
          value(event.payload, 'reason', '患者请求护士协助')
        );
      }
      break;
    }
    case 'handoff_resolved':
      taskStore.resolveHandoff(event.task_id);
      break;
    case 'task_status_updated':
      taskStore.updateTask(event.task_id, {
        taskStatus: value(
          event.payload,
          'task_status',
          'in_progress'
        ) as CareTaskStatus,
        aiSummary: value(event.payload, 'ai_summary', undefined),
      });
      break;
    case 'error':
    case 'heartbeat':
    case 'assistant_audio_delta':
    case 'education_status_updated':
      break;
  }
}

type CareTaskStatus = Parameters<
  ReturnType<typeof useTaskStore.getState>['updateTaskStatus']
>[1];
