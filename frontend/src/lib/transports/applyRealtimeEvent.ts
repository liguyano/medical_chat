import type { SseEnvelope } from '@/lib/api/contracts';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type {
  ConsentClause,
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
  const isFinal = Boolean(event.payload.is_final);
  const message = buildMessage(event, role, !isFinal);
  const existing = currentSession(event.task_id)?.messages.find(
    (item) => item.id === message.id
  );
  const fullContent = value(event.payload, 'content_text', '');
  const delta = value(event.payload, 'delta', value(event.payload, 'text', ''));
  const isSnapshot = Boolean(event.payload.snapshot);
  store.upsertMessage(event.task_id, {
    ...message,
    contentText:
      (isFinal || isSnapshot) && fullContent
        ? fullContent
        : existing?.contentText === delta
          ? existing.contentText
          : `${existing?.contentText ?? ''}${delta}`,
  });
  if (role === 'ai') store.setStreaming(isFinal ? null : event.task_id);
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
      if (!currentSession(event.task_id)) {
        chatStore.setSession(event.task_id, session);
      }
      const message = buildMessage(event, 'ai', false);
      const existing = currentSession(event.task_id)?.messages.find(
        (item) => item.id === message.id
      );
      chatStore.upsertMessage(event.task_id, {
        ...message,
        contentText: message.contentText || existing?.contentText || '',
        isStreaming: false,
      });
      const completedSession = currentSession(event.task_id) ?? session;
      if (completedSession.sessionStatus === 'pending') {
        chatStore.setSession(event.task_id, {
          ...completedSession,
          sessionStatus: 'active',
        });
      }
      chatStore.setStreaming(null);
      break;
    }
    case 'extraction_updated': {
      const fields = Array.isArray(event.payload.fields)
        ? event.payload.fields
        : [event.payload.field ?? event.payload];
      for (const item of fields) {
        const raw =
          item && typeof item === 'object'
            ? (item as Record<string, unknown>)
            : {};
        const answer: StructuredAnswer = {
          questionId: String(raw.question_id ?? raw.field_id ?? ''),
          questionCode: String(raw.question_code ?? ''),
          questionText: String(raw.question_text ?? raw.field_name ?? '评估字段'),
          answerText:
            raw.answer_text === undefined || raw.answer_text === null
              ? undefined
              : String(raw.answer_text),
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
        if (answer.questionId) {
          chatStore.upsertStructuredAnswer(event.task_id, answer);
        }
      }
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
    case 'education_triggered': {
      const materialId = value(
        event.payload,
        'material_id',
        event.event_id
      );
      chatStore.upsertEducationCard(event.task_id, {
        id: event.event_id || `EDU-${materialId}`,
        taskId: event.task_id,
        materialId,
        category: value(event.payload, 'category', ''),
        title: value(event.payload, 'title', '医学宣教'),
        documentVersion: value(event.payload, 'document_version', ''),
        originalContent: value(event.payload, 'original_content', ''),
        patientContent: value(event.payload, 'patient_content', ''),
        spokenContent: value(event.payload, 'spoken_content', ''),
        sourceName: value(event.payload, 'source_name', undefined),
        priority: value(
          event.payload,
          'priority',
          'medium'
        ) as 'low' | 'medium' | 'high',
        requiresAcknowledgement: value(
          event.payload,
          'requires_acknowledgement',
          true
        ),
        autoPlay: value(event.payload, 'auto_play', true),
        acknowledged: false,
        occurredAt: event.occurred_at,
      });
      chatStore.addEvent(event.task_id, {
        id: `EDUCATION-${materialId}`,
        taskId: event.task_id,
        messageId: event.message_id,
        eventType: 'education',
        title: value(event.payload, 'title', '医学宣教'),
        description: value(
          event.payload,
          'patient_content',
          value(event.payload, 'original_content', '')
        ),
        priority: value(
          event.payload,
          'priority',
          'medium'
        ) as InteractionEvent['priority'],
        handled: false,
        occurredAt: event.occurred_at,
      });
      break;
    }
    case 'education_status_updated':
      chatStore.updateEducationCard(
        event.task_id,
        value(event.payload, 'material_id', ''),
        {
          acknowledged: value(event.payload, 'acknowledged', false),
        }
      );
      break;
    case 'consent_triggered': {
      const rawClauses = Array.isArray(event.payload.clauses)
        ? event.payload.clauses
        : [];
      const clauses: ConsentClause[] = rawClauses.map((item, index) => {
        const raw =
          item && typeof item === 'object'
            ? (item as Record<string, unknown>)
            : {};
        return {
          id: String(raw.id ?? `clause-${index + 1}`),
          clauseCode: String(raw.clause_code ?? raw.clauseCode ?? ''),
          clauseName: String(
            raw.clause_name ?? raw.clauseName ?? `条款 ${index + 1}`
          ),
          patientContent: String(
            raw.patient_content ?? raw.patientContent ?? ''
          ),
          importanceLevel: String(
            raw.importance_level ?? raw.importanceLevel ?? 'important'
          ) as ConsentClause['importanceLevel'],
          mandatoryDelivery: Boolean(
            raw.mandatory_delivery ?? raw.mandatoryDelivery ?? true
          ),
          explicitConfirmationRequired: Boolean(
            raw.explicit_confirmation_required ??
              raw.explicitConfirmationRequired ??
              true
          ),
          deliveryStatus: String(
            raw.delivery_status ?? raw.deliveryStatus ?? 'pending'
          ) as ConsentClause['deliveryStatus'],
          listened: Boolean(raw.listened),
          confirmed: Boolean(raw.confirmed),
        };
      });
      chatStore.upsertConsentRequest(event.task_id, {
        id: event.event_id || `CONSENT-${Date.now()}`,
        taskId: event.task_id,
        formId: value(event.payload, 'form_id', event.event_id),
        formType: value(event.payload, 'form_type', ''),
        title: value(event.payload, 'title', '知情同意确认'),
        documentVersion: value(event.payload, 'document_version', ''),
        fullText: value(event.payload, 'full_text', ''),
        clauses,
        status: value(
          event.payload,
          'status',
          'pending_signature'
        ) as 'pending_signature',
        requiresSignature: value(
          event.payload,
          'requires_signature',
          true
        ),
        autoPlay: value(event.payload, 'auto_play', true),
        occurredAt: event.occurred_at,
      });
      break;
    }
    case 'consent_status_updated':
      chatStore.updateConsentRequest(
        event.task_id,
        value(event.payload, 'form_id', ''),
        {
          status: value(
            event.payload,
            'status',
            'pending_signature'
          ) as 'signed' | 'refused' | 'needs_explanation',
        }
      );
      break;
    case 'handoff_requested': {
      const requestId = value(
        event.payload,
        'request_id',
        event.event_id || `NURSE-${Date.now()}`
      );
      const reason = value(
        event.payload,
        'reason',
        '患者请求护士协助'
      );
      chatStore.addEvent(event.task_id, {
        id: `HANDOFF-${requestId}`,
        taskId: event.task_id,
        messageId: event.message_id,
        eventType: 'handoff',
        title: value(event.payload, 'title', '请求护士协助'),
        description: value(event.payload, 'description', reason),
        priority: value(
          event.payload,
          'priority',
          'high'
        ) as InteractionEvent['priority'],
        handled: false,
        occurredAt: event.occurred_at,
        metadata: {
          requestId: value(event.payload, 'request_id', ''),
          requestedAction: value(
            event.payload,
            'requested_action',
            'other'
          ),
          actionLabel: value(
            event.payload,
            'action_label',
            '人工护理操作'
          ),
          urgency: value(event.payload, 'urgency', 'routine'),
          patientName: value(event.payload, 'patient_name', ''),
          bedNo: value(event.payload, 'bed_no', ''),
          wardName: value(event.payload, 'ward_name', ''),
        },
      });
      taskStore.requestHandoff(event.task_id, reason, {
        requestId: value(event.payload, 'request_id', ''),
        requestedAction: value(
          event.payload,
          'requested_action',
          'other'
        ),
        actionLabel: value(
          event.payload,
          'action_label',
          '人工护理操作'
        ),
        urgency: value(
          event.payload,
          'urgency',
          'routine'
        ) as 'routine' | 'urgent',
      });
      chatStore.upsertNurseAssistanceRequest({
        requestId,
        taskId: event.task_id,
        patientName: value(event.payload, 'patient_name', undefined),
        bedNo: value(event.payload, 'bed_no', undefined),
        wardName: value(event.payload, 'ward_name', undefined),
        reason,
        requestedAction: value(
          event.payload,
          'requested_action',
          'other'
        ),
        actionLabel: value(
          event.payload,
          'action_label',
          '人工护理操作'
        ),
        urgency: value(
          event.payload,
          'urgency',
          'routine'
        ) as 'routine' | 'urgent',
        status: 'requested',
        occurredAt: event.occurred_at,
      });
      break;
    }
    case 'handoff_resolved': {
      taskStore.resolveHandoff(event.task_id);
      const requestId = value(event.payload, 'request_id', '');
      if (requestId) {
        chatStore.resolveNurseAssistanceRequest(requestId);
      } else {
        for (const request of Object.values(
          chatStore.nurseAssistanceRequests
        )) {
          if (request.taskId === event.task_id) {
            chatStore.resolveNurseAssistanceRequest(request.requestId);
          }
        }
      }
      break;
    }
    case 'task_status_updated': {
      const taskStatus = value(
        event.payload,
        'task_status',
        'in_progress'
      ) as CareTaskStatus;
      const aiSummary = value(event.payload, 'ai_summary', undefined);
      taskStore.updateTask(event.task_id, {
        taskStatus,
        aiSummary,
      });
      if (taskStatus === 'pending_review' || taskStatus === 'completed') {
        chatStore.setSession(event.task_id, {
          ...session,
          sessionStatus: 'completed',
          completedAt: event.occurred_at,
          aiSummary: aiSummary ?? session.aiSummary,
        });
        chatStore.setStreaming(null);
      }
      break;
    }
    case 'error':
      chatStore.setStreaming(null);
      break;
    case 'heartbeat':
    case 'assistant_audio_delta':
      break;
  }
}

type CareTaskStatus = Parameters<
  ReturnType<typeof useTaskStore.getState>['updateTaskStatus']
>[1];
