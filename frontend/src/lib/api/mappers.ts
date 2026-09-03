import type {
  ApiId,
  QuestionProgressDto,
  BackendTaskDto,
  AssessmentScaleDto,
  CreateTaskRequest,
  DialogHistoryResponse,
  DialogMessageDto,
  ExtractedFieldDto,
  InHospitalPatientDto,
  PatientRecordDto,
  MessageRatingDto,
  PatientLoginResponse,
  QualityReviewDto,
  QuestionnaireDto,
  StaffLoginResponse,
} from '@/lib/api/contracts';
import type {
  AssessmentScale,
  AssessmentQuestion,
  AssessmentOption,
  CareTask,
  CollectionMode,
  InteractionMessage,
  InteractionSession,
  MessageFeedback,
  Patient,
  PatientEncounter,
  QualityReview,
  QuestionnaireSnapshot,
  StructuredAnswer,
  TaskPreparation,
  User,
} from '@/lib/types';
import type { QuestionProgress } from '@/lib/types/questionProgress';

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

function mapTaskPreparation(
  dto: BackendTaskDto['preparation']
): TaskPreparation | undefined {
  if (!dto) return undefined;
  return {
    status: dto.status,
    stage: dto.stage,
    attempt: dto.attempt ?? 0,
    error: dto.error,
    patientVisibleAt: dto.patient_visible_at,
    stages: Object.fromEntries(
      Object.entries(dto.stages ?? {}).map(([stage, snapshot]) => [
        stage,
        {
          status: snapshot.status,
          output: snapshot.output ?? {},
          error: snapshot.error,
          updatedAt: snapshot.updated_at,
        },
      ])
    ),
  };
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
    preparation: mapTaskPreparation(dto.preparation),
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
    needManualIntervention: dto.need_manual_intervention ?? false,
    interventionReason: dto.intervention_reason,
    progress:
      dto.total_question_count !== undefined
        ? {
            current: dto.answered_question_count ?? 0,
            total: dto.total_question_count,
          }
        : undefined,
  };
}

function mapQuestionType(value: string): AssessmentQuestion['questionType'] {
  if (value === 'number' || value === 'integer' || value === 'decimal') return 'number';
  if (value === 'date' || value === 'datetime') return 'date';
  if (value === 'boolean') return 'boolean';
  if (value === 'multiple_choice') return 'multiple_choice';
  if (value === 'single_choice' || value === 'grouped_choice') return 'single_choice';
  return 'text';
}

function mapQuestionnaireValue(
  answer: QuestionnaireDto['answers'][number]
): import('@/lib/types').PrototypeAnswerValue {
  if (answer.selected_options?.length) {
    return answer.answer_type === 'multiple_choice'
      ? answer.selected_options
      : answer.selected_options[0];
  }
  if (answer.answer_text !== null && answer.answer_text !== undefined) {
    return answer.answer_text;
  }
  if (answer.answer_number !== null && answer.answer_number !== undefined) {
    return answer.answer_number;
  }
  if (answer.answer_boolean !== null && answer.answer_boolean !== undefined) {
    return answer.answer_boolean;
  }
  if (answer.answer_date !== null && answer.answer_date !== undefined) {
    return answer.answer_date;
  }
  return null;
}

export function mapQuestionnaireDto(dto: QuestionnaireDto): QuestionnaireSnapshot {
  const questions = dto.questions.map((question) => {
    const validation = question.validation_rule ?? {};
    const options: AssessmentOption[] = (question.options ?? []).map((option) => ({
      id: id(option.id),
      optionCode: option.option_code,
      optionLabel: option.option_label,
      displayOrder: undefined,
      clinicalScore: option.clinical_score ?? undefined,
      requiresFollowUp: option.requires_follow_up ?? false,
    }));
    return {
      id: id(question.id),
      questionCode: question.question_code,
      sectionId:
        question.section_id === null || question.section_id === undefined
          ? undefined
          : id(question.section_id),
      sectionName: question.section_name ?? undefined,
      questionText: question.question_text,
      questionType: mapQuestionType(question.question_type),
      required: question.required,
      scored: question.scored,
      derived: question.derived,
      displayOrder: question.sort_no,
      unit: question.unit ?? undefined,
      options,
      validationRule: {
        min: typeof validation.min === 'number' ? validation.min : undefined,
        max: typeof validation.max === 'number' ? validation.max : undefined,
        minLength:
          typeof validation.min_length === 'number'
            ? validation.min_length
            : typeof validation.minLength === 'number'
              ? validation.minLength
              : undefined,
        maxLength:
          typeof validation.max_length === 'number'
            ? validation.max_length
            : typeof validation.maxLength === 'number'
              ? validation.maxLength
              : undefined,
      },
    };
  });
  const answers = dto.answers.map((answer) => ({
    questionId: id(answer.question_id),
    questionCode: answer.question_code,
    answerType: answer.answer_type,
    answerText: answer.answer_text ?? undefined,
    answerNumber: answer.answer_number ?? undefined,
    answerBoolean: answer.answer_boolean ?? undefined,
    answerDate: answer.answer_date ?? undefined,
    selectedOptions: answer.selected_options ?? [],
    selectedOptionLabels: answer.selected_option_labels ?? [],
    selectedOptionValues: answer.selected_option_values ?? [],
    displayValue: answer.display_value ?? undefined,
    clinicalScore: answer.clinical_score ?? undefined,
  }));
  return {
    taskId: id(dto.task_id),
    taskNo: dto.task_no,
    status: dto.status,
    questions,
    answers,
    answerValues: Object.fromEntries(
      dto.answers.map((answer) => [
        answer.question_code,
        mapQuestionnaireValue(answer),
      ])
    ),
    scores: dto.scores.map((score) => ({
      scaleId: id(score.scale_id),
      scaleName: score.scale_name,
      totalScore: score.total_score ?? undefined,
      riskLevel: score.risk_level ?? undefined,
      resultSummary: score.result_summary ?? undefined,
    })),
    submittedAt: dto.submitted_at ?? undefined,
    updatedAt: dto.updated_at ?? undefined,
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
  taskSummary?: {
    total: number;
    pendingReview: number;
    inProgress: number;
    handoffRequired: boolean;
  };
} {
  const patientId = id(dto.patient.id);
  const diagnosis = dto.encounter.diagnosis_snapshot;
  const diagnosisText =
    typeof diagnosis?.primary_diagnosis === 'string'
      ? diagnosis.primary_diagnosis
      : typeof diagnosis?.primary === 'string'
        ? diagnosis.primary
      : typeof diagnosis?.diagnosis === 'string'
        ? diagnosis.diagnosis
        : '';
  return {
    patient: {
      id: patientId,
      patientNo: dto.patient.patient_no,
      hisPatientId: dto.patient.his_patient_id,
      name: dto.patient.patient_name,
      gender:
        dto.patient.sex === '女'
          ? 'female'
          : dto.patient.sex === '男'
            ? 'male'
            : 'other',
      age: calculateAge(dto.patient.birthday),
      birthday: dto.patient.birthday,
      idCard: dto.patient.id_card_masked,
      phone: dto.patient.phone,
      emergencyContactName: dto.patient.emergency_contact_name,
      emergencyContactRelation: dto.patient.emergency_contact_relation,
      emergencyContactPhone: dto.patient.emergency_contact_phone,
      address: dto.patient.address,
    },
    encounter: {
      id: id(dto.encounter.id),
      patientId,
      encounterNo: dto.encounter.encounter_no,
      inpatientNo: dto.encounter.inpatient_no ?? dto.encounter.encounter_no,
      departmentCode: dto.encounter.department_code,
      department: dto.encounter.department_name ?? '',
      ward: dto.encounter.ward_name ?? '',
      bedNo: dto.encounter.bed_no ?? '',
      admissionDate: dto.encounter.admission_time,
      dischargeDate: dto.encounter.discharge_time,
      diagnosis: diagnosisText,
      diagnosisSnapshot: diagnosis,
      encounterStatus:
        dto.encounter.encounter_status === '待入院'
          ? 'pending_admission'
          : dto.encounter.encounter_status === '在院'
            ? 'in_hospital'
            : dto.encounter.encounter_status === '取消'
              ? 'cancelled'
              : 'discharged',
      admissionSource: dto.encounter.admission_source,
      nursingLevel: dto.encounter.nursing_level,
      insuranceType: dto.encounter.insurance_type,
      allergySummary: dto.encounter.allergy_summary,
    },
    taskSummary: dto.task_summary
      ? {
          total: dto.task_summary.total,
          pendingReview: dto.task_summary.pending_review,
          inProgress: dto.task_summary.in_progress,
          handoffRequired: dto.task_summary.handoff_required,
        }
      : undefined,
  };
}

export const mapPatientRecord = (dto: PatientRecordDto) =>
  mapInHospitalPatient(dto);

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
    answerType: field.answer_type as StructuredAnswer['answerType'],
    options: field.options,
    invalid: field.invalid ?? false,
    invalidReason: field.invalid_reason,
    rawAnswer: field.raw_answer,
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
export function mapQuestionProgress(dto: QuestionProgressDto): QuestionProgress {
  return {
    sessionId: dto.session_id,
    current: dto.current,
    total: dto.total,
    turnNumber: dto.turn_number,
    activeQuestionId: dto.active_question_id === null ? null : String(dto.active_question_id),
    candidateQuestionIds: dto.candidate_question_ids.map(String),
    questions: dto.questions.map((question) => ({
      questionId: String(question.question_id),
      questionCode: question.question_code,
      questionText: question.question_text,
      scaleName: question.scale_name,
      required: question.required,
      status: question.status,
      isCurrent: question.is_current,
      coolingUntilTurn: question.cooling_until_turn,
    })),
  };
}
