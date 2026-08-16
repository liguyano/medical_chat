import type {
  BackendTaskDto,
  CreateTaskRequest,
  DialogHistoryResponse,
  DialogMessageDto,
  ExtractedFieldDto,
} from '@/lib/api/contracts';
import type {
  CareTask,
  CollectionMode,
  InteractionMessage,
  InteractionSession,
  StructuredAnswer,
} from '@/lib/types';

function id(value: string | number | undefined, fallback = ''): string {
  return value === undefined ? fallback : String(value);
}

export function toBackendCollectionMode(
  mode: CollectionMode
): 'questionnaire' | 'ai_dialog' {
  return mode === 'traditional_form' ? 'questionnaire' : 'ai_dialog';
}

export function toCollectionMode(
  mode: BackendTaskDto['collection_mode']
): CollectionMode {
  return mode === 'questionnaire' || mode === 'traditional_form'
    ? 'traditional_form'
    : 'ai_dialogue';
}

export function mapCreateTaskRequest(
  input: Omit<CreateTaskRequest, 'collection_mode'> & {
    collection_mode: CollectionMode;
  }
): CreateTaskRequest {
  return {
    ...input,
    collection_mode: toBackendCollectionMode(input.collection_mode),
  };
}

export function mapTaskDto(dto: BackendTaskDto): CareTask {
  const taskId = id(dto.task_id ?? dto.id);
  return {
    id: taskId,
    taskNo: dto.task_no,
    sessionId: id(dto.session_id) || undefined,
    patientId: id(dto.patient_id),
    encounterId: id(dto.encounter_id),
    encounterNo: dto.encounter_no,
    patientName: dto.patient_name ?? `患者 ${id(dto.patient_id)}`,
    bedNo: dto.bed_no ?? '待分配',
    department: dto.department,
    wardName: dto.ward_name,
    taskType: dto.task_type ?? '入院评估任务包',
    collectionMode: toCollectionMode(dto.collection_mode),
    taskStatus: dto.task_status,
    assignedNurseId: id(dto.assigned_nurse_id ?? dto.nurse_id),
    assignedNurseName: dto.assigned_nurse_name ?? '责任护士',
    scaleIds: dto.scale_ids?.map(String),
    scaleNames: dto.scale_names,
    scaleVersion: dto.scale_version,
    participantType: dto.participant_type,
    participantName: dto.participant_name,
    relationshipToPatient: dto.relationship_to_patient,
    assessmentScene: dto.assessment_scene,
    consentRequired: dto.consent_required,
    educationTopics: dto.education_topics,
    plannedStartTime: dto.planned_start_time,
    notes: dto.notes,
    handoffRequired: dto.handoff_required,
    handoffReason: dto.handoff_reason,
    currentStage: dto.current_stage as CareTask['currentStage'],
    aiSummary: dto.ai_summary,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    completedAt: dto.completed_at,
    progress:
      dto.total_question_count !== undefined
        ? {
            current: dto.answered_question_count ?? 0,
            total: dto.total_question_count,
          }
        : undefined,
  };
}

export function mapDialogMessage(dto: DialogMessageDto): InteractionMessage {
  const role =
    dto.role === 'assistant' || dto.role === 'ai'
      ? 'ai'
      : dto.role === 'user'
        ? 'patient'
        : dto.role;
  return {
    id: dto.message_id,
    messageNo: dto.message_id,
    sessionId: id(dto.session_id),
    turnNo: dto.turn_no,
    role,
    cicareStage: dto.cicare_stage as InteractionMessage['cicareStage'],
    intentType: dto.intent_type as InteractionMessage['intentType'],
    contentText: dto.content_text,
    audioUrl: dto.audio_url,
    occurredAt: dto.occurred_at,
    relatedQuestionIds: dto.related_question_ids?.map(String),
  };
}

export function mapDialogHistory(
  response: DialogHistoryResponse,
  task: CareTask
): InteractionSession {
  return {
    id: id(response.session_id),
    sessionNo: id(response.session_id),
    taskId: id(response.task_id),
    patientId: task.patientId,
    encounterId: task.encounterId,
    interactionType: 'assessment',
    channelType: 'mixed',
    sessionStatus:
      (response.session_status as InteractionSession['sessionStatus']) ??
      'active',
    currentCicareStage:
      (response.current_cicare_stage as InteractionSession['currentCicareStage']) ??
      'connect',
    answeredQuestionCount: response.answered_question_count,
    totalQuestionCount: response.total_question_count,
    aiSummary: response.ai_summary,
    messages: response.messages.map(mapDialogMessage),
  };
}

export function mapExtractedField(
  field: ExtractedFieldDto
): StructuredAnswer {
  return {
    questionId: id(field.question_id),
    questionCode: field.question_code,
    questionText: field.question_text,
    answerText: field.answer_text,
    answerNumber: field.answer_number,
    answerBoolean: field.answer_boolean,
    selectedOptions: field.selected_options,
    sourceMessageIds: field.source_message_ids ?? [],
    extractionConfidence: field.confidence ?? 0,
    corrected: field.corrected ?? false,
  };
}
