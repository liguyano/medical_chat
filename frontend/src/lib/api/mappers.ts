import type {
  ApiId,
  BackendTaskDto,
  AssessmentScaleDto,
  CreateTaskRequest,
  DialogHistoryResponse,
  DialogMessageDto,
  ExtractedFieldDto,
  InHospitalPatientDto,
  MessageRatingDto,
  PatientLoginResponse,
  QualityReviewDto,
  StaffLoginResponse,
} from '@/lib/api/contracts';
import type {
  AssessmentScale,
  CareTask,
  CollectionMode,
  InteractionMessage,
  InteractionSession,
  MessageFeedback,
  Patient,
  PatientEncounter,
  QualityReview,
  StructuredAnswer,
  User,
} from '@/lib/types';

function id(value: string | number | undefined, fallback = ''): string {
  return value === undefined ? fallback : String(value);
}

function numericId(value: string | number, fieldName: string): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${fieldName} 必须是有效的数字 ID`);
  }
  return parsed;
}

function optionalNumericId(value: string | number | undefined): number | undefined {
  if (value === undefined) return undefined;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
}

export function toReviewerId(value: string | number | undefined): number {
  if (value === undefined) return 0;
  const direct = Number(value);
  if (Number.isSafeInteger(direct) && direct >= 0) return direct;
  const numericSuffix = String(value).match(/\d+/g)?.join('');
  const parsed = numericSuffix ? Number(numericSuffix) : 0;
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
}

export function toBackendCollectionMode(
  mode: CollectionMode
): CollectionMode {
  return mode;
}

export function toCollectionMode(
  mode: BackendTaskDto['collection_mode']
): CollectionMode {
  return mode === 'traditional_form'
    ? 'traditional_form'
    : 'ai_dialogue';
}

export function mapCreateTaskRequest(
  input: Omit<
    CreateTaskRequest,
    | 'patient_id'
    | 'encounter_id'
    | 'assigned_nurse_id'
    | 'scale_ids'
    | 'collection_mode'
  > & {
    patient_id: ApiId;
    encounter_id: ApiId;
    assigned_nurse_id?: ApiId;
    scale_ids: ApiId[];
    collection_mode: CollectionMode;
  }
): CreateTaskRequest {
  return {
    ...input,
    patient_id: numericId(input.patient_id, 'patient_id'),
    encounter_id: numericId(input.encounter_id, 'encounter_id'),
    assigned_nurse_id: optionalNumericId(input.assigned_nurse_id),
    scale_ids: input.scale_ids.map((scaleId) =>
      numericId(scaleId, 'scale_ids')
    ),
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
    inpatientNo: dto.inpatient_no,
    patientName: dto.patient_name ?? `患者 ${id(dto.patient_id)}`,
    bedNo: dto.bed_no ?? '待分配',
    department: dto.department,
    wardName: dto.ward_name,
    sex: dto.sex,
    age: dto.age,
    admissionDate: dto.admission_time,
    encounterStatus: dto.encounter_status,
    taskType:
      dto.task_type === 'assessment'
        ? '入院评估任务包'
        : dto.task_type ?? '入院评估任务包',
    collectionMode: toCollectionMode(dto.collection_mode),
    taskStatus: dto.task_status,
    assignedNurseId: id(dto.assigned_nurse_id ?? dto.nurse_id),
    assignedNurseName: dto.assigned_nurse_name ?? '责任护士',
    scaleIds: dto.scale_ids?.map(String),
    scaleNames: dto.scale_names,
    scaleProgress: dto.scale_progress?.map((item) => ({
      scaleId: id(item.scale_id),
      scaleName: item.scale_name,
      answeredQuestionCount: item.answered_question_count,
      totalQuestionCount: item.total_question_count,
      status: item.status,
    })),
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
  const backendRole = dto.role ?? dto.role_type ?? 'system';
  const role =
    backendRole === 'assistant' || backendRole === 'ai' || backendRole === 'AI'
      ? 'ai'
      : backendRole === 'user' || backendRole === '患者'
        ? 'patient'
        : backendRole === '家属'
          ? 'patient'
          : 'system';
  const messageId = dto.message_id ?? dto.message_no ?? '';
  return {
    id: messageId,
    messageNo: messageId,
    sessionId: id(dto.session_id),
    turnNo: dto.turn_no,
    role,
    cicareStage: dto.cicare_stage as InteractionMessage['cicareStage'],
    intentType: dto.intent_type as InteractionMessage['intentType'],
    contentText: dto.content_text ?? dto.asr_text ?? dto.tts_text ?? '',
    audioUrl: dto.audio_url,
    occurredAt: dto.occurred_at ?? new Date().toISOString(),
    relatedQuestionIds: dto.related_question_ids?.map(String),
  };
}

export function mapDialogHistory(
  response: DialogHistoryResponse,
  task: CareTask
): InteractionSession {
  return {
    id: id(response.session_id ?? response.session_no, task.sessionId),
    sessionNo: id(response.session_id ?? response.session_no, task.sessionId),
    taskId: id(response.task_id, task.id),
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
    messages: response.messages.map((message) =>
      mapDialogMessage({
        ...message,
        session_id: response.session_id ?? response.session_no,
      })
    ),
  };
}

function calculateAge(birthday?: string): number {
  if (!birthday) return 0;
  const birth = new Date(birthday);
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  if (
    now.getMonth() < birth.getMonth() ||
    (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())
  ) {
    age -= 1;
  }
  return Math.max(age, 0);
}

export function mapInHospitalPatient(dto: InHospitalPatientDto): {
  patient: Patient;
  encounter: PatientEncounter;
} {
  const patientId = id(dto.patient.id);
  const diagnosis = dto.encounter.diagnosis_snapshot;
  const diagnosisText =
    typeof diagnosis?.primary_diagnosis === 'string'
      ? diagnosis.primary_diagnosis
      : typeof diagnosis?.diagnosis === 'string'
        ? diagnosis.diagnosis
        : '';
  return {
    patient: {
      id: patientId,
      patientNo: dto.patient.patient_no,
      name: dto.patient.patient_name,
      gender:
        dto.patient.sex === '女'
          ? 'female'
          : dto.patient.sex === '男'
            ? 'male'
            : 'other',
      age: calculateAge(dto.patient.birthday),
      phone: dto.patient.phone,
    },
    encounter: {
      id: id(dto.encounter.id),
      patientId,
      encounterNo: dto.encounter.encounter_no,
      inpatientNo: dto.encounter.inpatient_no ?? dto.encounter.encounter_no,
      department: dto.encounter.department_name ?? '',
      ward: dto.encounter.ward_name ?? '',
      bedNo: dto.encounter.bed_no ?? '',
      admissionDate: dto.encounter.admission_time,
      diagnosis: diagnosisText,
      encounterStatus:
        dto.encounter.encounter_status === '在院'
          ? 'in_hospital'
          : 'discharged',
    },
  };
}

export function mapPatientPortal(response: PatientLoginResponse): {
  patient: Patient;
  encounter: PatientEncounter;
  tasks: CareTask[];
} {
  const record = mapInHospitalPatient({
    patient: response.patient,
    encounter: response.encounter,
  });
  return {
    ...record,
    tasks: response.tasks.map(mapTaskDto),
  };
}

export function mapStaffUser(response: StaffLoginResponse): User {
  return {
    id: id(response.staff.id),
    username: response.staff.staff_no,
    role: response.staff.role_code === 'patient' ? 'patient' : 'nurse',
    name: response.staff.staff_name,
    department: response.staff.department_name,
    avatar: '',
  };
}

export function mapAssessmentScale(dto: AssessmentScaleDto): AssessmentScale {
  return {
    id: id(dto.id),
    scaleCode: dto.scale_code,
    scaleName: dto.scale_name,
    scaleType: dto.scale_type,
    description: dto.description ?? `${dto.question_count} 道评估问题`,
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
    selectedOptionLabels: field.selected_option_labels,
    selectedOptionValues: field.selected_option_values,
    displayValue: field.display_value,
    sourceMessageIds: field.source_message_ids ?? [],
    extractionConfidence: field.confidence ?? 0,
    corrected: field.corrected ?? false,
  };
}

export function mapMessageRating(dto: MessageRatingDto): MessageFeedback {
  return {
    messageId: id(dto.message_id),
    taskId: id(dto.task_id),
    reviewerId: id(dto.reviewer_id),
    feedbackType: dto.rating,
    score: dto.score,
    issueTags: dto.issue_tags ?? [],
    comment: dto.comment,
    reviewedAt: dto.reviewed_at,
  };
}

export function mapQualityReview(dto: QualityReviewDto): QualityReview {
  return {
    taskId: id(dto.task_id),
    reviewerId: id(dto.reviewer_id),
    dialogueScores: dto.dialogue_scores ?? {},
    assessmentScores: dto.assessment_scores ?? {},
    dialogueComments: dto.dialogue_comments ?? {},
    assessmentComments: dto.assessment_comments ?? {},
    comment: dto.comment,
    submittedAt: dto.submitted_at,
  };
}
