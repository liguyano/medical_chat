import type {
  AssessmentScaleDto,
  BackendTaskDto,
  CreateTaskResponse,
  DialogHistoryResponse,
  EducationMaterialConfigDto,
  ExtractedFieldsResponse,
  InHospitalPatientDto,
  InteractionRuleConfigDto,
  InteractionRuleMatchDto,
  MessageRatingListResponse,
  NursingPlanDto,
  PatientLoginResponse,
  PatientRecordDto,
  QualityReviewDto,
  AssessmentScaleConfigSummaryDto,
  SseEnvelope,
  StaffLoginResponse,
} from '@/lib/api/contracts';
import { apiRequest } from '@/lib/api/httpClient';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  mapCreateTaskRequest,
  mapAssessmentScale,
  mapDialogHistory,
  mapExtractedField,
  mapInHospitalPatient,
  mapMessageRating,
  mapPatientPortal,
  mapPatientRecord,
  mapQualityReview,
  mapStaffUser,
  mapTaskDto,
  toReviewerId,
} from '@/lib/api/mappers';
import type {
  AssessmentScale,
  AssessmentScaleConfigSummary,
  CareTask,
  EducationMaterialConfig,
  InteractionRuleConfig,
  InteractionRuleMatch,
  NursingPlan,
  NursingPlanUpdate,
} from '@/lib/types';
import type {
  CareRepository,
  CreateTaskInput,
  PatientLoginInput,
  PatientListFilters,
  PatientRecordInput,
  PatientWithEncounter,
  StaffLoginInput,
} from '@/lib/repositories/types';

function mapEducationMaterial(
  item: EducationMaterialConfigDto
): EducationMaterialConfig {
  return {
    id: String(item.id),
    versionId: String(item.version_id),
    unitId: String(item.unit_id),
    category: item.category,
    title: item.title,
    documentVersion: item.document_version,
    originalContent: item.original_content,
    patientContent: item.patient_content,
    spokenContent: item.spoken_content,
    sourceName: item.source_name ?? undefined,
    priority: item.priority,
    requiresAcknowledgement: item.requires_acknowledgement,
    autoPlay: item.auto_play,
    enabled: item.enabled,
  };
}

function toBackendEncounterStatus(
  status: PatientRecordInput['encounter']['encounterStatus']
): '待入院' | '在院' | '已出院' | '取消' {
  if (status === 'pending_admission') return '待入院';
  if (status === 'in_hospital') return '在院';
  if (status === 'cancelled') return '取消';
  return '已出院';
}

function patientRecordBody(input: PatientRecordInput, updating: boolean) {
  return {
    patient: {
      his_patient_id: input.patient.hisPatientId || null,
      patient_name: input.patient.name,
      sex:
        input.patient.gender === 'male'
          ? '男'
          : input.patient.gender === 'female'
            ? '女'
            : '其他',
      birthday: input.patient.birthday,
      ...(input.patient.idCardNo
        ? { id_card_no: input.patient.idCardNo }
        : {}),
      phone: input.patient.phone,
      emergency_contact_name: input.patient.emergencyContactName || null,
      emergency_contact_relation:
        input.patient.emergencyContactRelation || null,
      emergency_contact_phone: input.patient.emergencyContactPhone || null,
      address: input.patient.address || null,
    },
    encounter: {
      ...(updating
        ? { id: Number(input.encounter.id) }
        : {}),
      inpatient_no: input.encounter.inpatientNo,
      department_code: input.encounter.departmentCode || null,
      department_name: input.encounter.department,
      ward_name: input.encounter.ward,
      bed_no: input.encounter.bedNo,
      admission_time: input.encounter.admissionDate,
      discharge_time: input.encounter.dischargeDate || null,
      encounter_status: toBackendEncounterStatus(
        input.encounter.encounterStatus
      ),
      diagnosis_snapshot: {
        primary: input.encounter.primaryDiagnosis,
        secondary: input.encounter.secondaryDiagnoses,
        risk_note: input.encounter.riskNote || '',
      },
      admission_source: input.encounter.admissionSource || null,
      nursing_level: input.encounter.nursingLevel || null,
      insurance_type: input.encounter.insuranceType || null,
      allergy_summary: input.encounter.allergySummary || null,
    },
  };
}

function mapInteractionRule(
  item: InteractionRuleConfigDto
): InteractionRuleConfig {
  return {
    id: String(item.id),
    ruleCode: item.rule_code,
    ruleName: item.rule_name,
    scopeType: item.scope_type,
    scopeId:
      item.scope_id === null || item.scope_id === undefined
        ? undefined
        : String(item.scope_id),
    keywords: item.keywords,
    patterns: item.patterns,
    actionType: item.action_type,
    prompt: item.prompt,
    tags: item.tags,
    priority: item.priority,
    enabled: item.enabled,
  };
}

function mapInteractionRuleMatch(
  item: InteractionRuleMatchDto
): InteractionRuleMatch {
  return {
    ruleCode: item.rule_code,
    ruleName: item.rule_name,
    matchedTerms: item.matched_terms,
    actionType: item.action_type,
    prompt: item.prompt,
    priority: item.priority,
  };
}

function mapScaleConfigSummary(
  item: AssessmentScaleConfigSummaryDto
): AssessmentScaleConfigSummary {
  return {
    id: String(item.id),
    scaleCode: item.scale_code,
    scaleName: item.scale_name,
    scaleType: item.scale_type,
    clinicalPurpose: item.clinical_purpose ?? undefined,
    status: item.status,
    versionId: String(item.version_id),
    versionCode: item.version_code,
    versionName: item.version_name,
    publishStatus: item.publish_status,
    sectionCount: item.section_count,
    questionCount: item.question_count,
    optionCount: item.option_count,
    ruleCount: item.rule_count,
    actionCount: item.action_count,
  };
}

function mapNursingPlan(item: NursingPlanDto): NursingPlan {
  return {
    id: Number(item.id),
    taskId: Number(item.task_id),
    planNo: item.plan_no,
    planStatus: item.plan_status,
    riskSummary: item.risk_summary,
    educationSummary: item.education_summary,
    handoverSummary: item.handover_summary,
    generatedBy: item.generated_by,
    confirmedBy:
      item.confirmed_by === null || item.confirmed_by === undefined
        ? null
        : Number(item.confirmed_by),
    confirmedAt: item.confirmed_at ?? null,
    profile: {
      id: Number(item.profile.id),
      profileNo: item.profile.profile_no,
      sourceSubmissionIds: item.profile.source_submission_ids.map(Number),
      cooperationLevel: item.profile.cooperation_level,
      cognitionLevel: item.profile.cognition_level,
      selfCareLevel: item.profile.self_care_level,
      fallRiskLevel: item.profile.fall_risk_level,
      pressureRiskLevel: item.profile.pressure_risk_level,
      nutritionRiskLevel: item.profile.nutrition_risk_level,
      communicationLevel: item.profile.communication_level,
      educationNeedLevel: item.profile.education_need_level,
      detail: item.profile.profile_detail,
      generatedBy: item.profile.generated_by,
      generatedAt: item.profile.generated_at,
    },
    items: item.items.map((planItem) => ({
      id: Number(planItem.id),
      itemType: planItem.item_type,
      itemCode: planItem.item_code,
      itemContent: planItem.item_content,
      sourceType: planItem.source_type,
      sourceId: planItem.source_id ?? null,
      priority:
        planItem.priority === 'high' || planItem.priority === 'low'
          ? planItem.priority
          : 'medium',
      nurseAction:
        planItem.nurse_action === 'accepted' ||
        planItem.nurse_action === 'modified' ||
        planItem.nurse_action === 'rejected'
          ? planItem.nurse_action
          : 'pending',
      nurseComment: planItem.nurse_comment ?? null,
    })),
  };
}

function buildTaskFallback(
  input: CreateTaskInput,
  response: CreateTaskResponse
): CareTask {
  return {
    id: String(response.task_id),
    taskNo: response.task_no,
    sessionId:
      response.session_id === undefined
        ? undefined
        : String(response.session_id),
    patientId: input.patient.id,
    encounterId: input.encounter.id,
    encounterNo: input.encounter.inpatientNo,
    patientName: input.patient.name,
    bedNo: input.encounter.bedNo,
    department: input.encounter.department,
    wardName: input.encounter.ward,
    taskType: '入院评估任务包',
    collectionMode: input.collectionMode,
    taskStatus: response.status ?? 'pending',
    assignedNurseId: input.nurseId,
    assignedNurseName: input.nurseName,
    scaleName: '入院评估任务包',
    scaleVersion: 'v1.0',
    scaleIds: input.scaleIds,
    scaleNames: input.scaleNames,
    participantType: input.participantType,
    participantName: input.participantName,
    relationshipToPatient: input.relationshipToPatient,
    assessmentScene: input.assessmentScene,
    consentRequired: input.consentRequired,
    educationTopics: input.educationTopics,
    plannedStartTime: input.plannedStartTime,
    notes: input.notes,
    createdAt: new Date().toISOString(),
    progress: { current: 0, total: input.scaleIds.length },
  };
}

export class ApiCareRepository implements CareRepository {
  async listPatients(
    filters: PatientListFilters = {},
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]> {
    const query = new URLSearchParams();
    if (filters.keyword) query.set('keyword', filters.keyword);
    if (filters.status !== undefined) query.set('status', filters.status);
    if (filters.departmentName) {
      query.set('department_name', filters.departmentName);
    }
    if (filters.wardName) query.set('ward_name', filters.wardName);
    const suffix = query.size ? `?${query.toString()}` : '';
    const response = await apiRequest<PatientRecordDto[]>(
      `/api/patients${suffix}`,
      { signal }
    );
    return response.map(mapPatientRecord);
  }

  async listInHospitalPatients(
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]> {
    const response = await apiRequest<InHospitalPatientDto[]>(
      '/api/patients/in-hospital',
      { signal }
    );
    return response.map(mapInHospitalPatient);
  }

  async getPatient(patientId: string, signal?: AbortSignal) {
    const response = await apiRequest<PatientRecordDto>(
      `/api/patients/${encodeURIComponent(patientId)}`,
      { signal }
    );
    return mapPatientRecord(response);
  }

  async createPatient(input: PatientRecordInput, signal?: AbortSignal) {
    const response = await apiRequest<PatientRecordDto>('/api/patients', {
      method: 'POST',
      body: patientRecordBody(input, false),
      signal,
    });
    return mapPatientRecord(response);
  }

  async updatePatient(
    patientId: string,
    input: PatientRecordInput,
    signal?: AbortSignal
  ) {
    const response = await apiRequest<PatientRecordDto>(
      `/api/patients/${encodeURIComponent(patientId)}`,
      {
        method: 'PUT',
        body: patientRecordBody(input, true),
        signal,
      }
    );
    return mapPatientRecord(response);
  }

  async listScales(signal?: AbortSignal): Promise<AssessmentScale[]> {
    const response = await apiRequest<AssessmentScaleDto[]>('/api/scales', {
      signal,
    });
    return response.map(mapAssessmentScale);
  }

  async listEducationMaterials(signal?: AbortSignal) {
    const response = await apiRequest<EducationMaterialConfigDto[]>(
      '/api/system-config/education-materials',
      { signal }
    );
    return response.map(mapEducationMaterial);
  }

  async updateEducationMaterial(
    materialId: string,
    input: Parameters<CareRepository['updateEducationMaterial']>[1],
    signal?: AbortSignal
  ) {
    const response = await apiRequest<EducationMaterialConfigDto>(
      `/api/system-config/education-materials/${encodeURIComponent(materialId)}`,
      {
        method: 'PUT',
        body: {
          title: input.title,
          document_version: input.documentVersion,
          original_content: input.originalContent,
          patient_content: input.patientContent,
          spoken_content: input.spokenContent,
          source_name: input.sourceName || null,
          priority: input.priority,
          requires_acknowledgement: input.requiresAcknowledgement,
          auto_play: input.autoPlay,
          enabled: input.enabled,
        },
        signal,
      }
    );
    return mapEducationMaterial(response);
  }

  async listInteractionRules(signal?: AbortSignal) {
    const response = await apiRequest<InteractionRuleConfigDto[]>(
      '/api/system-config/interaction-rules',
      { signal }
    );
    return response.map(mapInteractionRule);
  }

  async updateInteractionRule(
    ruleId: string,
    input: Parameters<CareRepository['updateInteractionRule']>[1],
    signal?: AbortSignal
  ) {
    const response = await apiRequest<InteractionRuleConfigDto>(
      `/api/system-config/interaction-rules/${encodeURIComponent(ruleId)}`,
      {
        method: 'PUT',
        body: {
          rule_name: input.ruleName,
          scope_type: input.scopeType,
          scope_id: input.scopeId ? Number(input.scopeId) : null,
          keywords: input.keywords,
          patterns: input.patterns,
          action_type: input.actionType,
          prompt: input.prompt,
          tags: input.tags,
          priority: input.priority,
          enabled: input.enabled,
        },
        signal,
      }
    );
    return mapInteractionRule(response);
  }

  async testInteractionRules(text: string, signal?: AbortSignal) {
    const response = await apiRequest<InteractionRuleMatchDto[]>(
      '/api/system-config/interaction-rules/test',
      { method: 'POST', body: { text }, signal }
    );
    return response.map(mapInteractionRuleMatch);
  }

  async listScaleConfigs(signal?: AbortSignal) {
    const response = await apiRequest<AssessmentScaleConfigSummaryDto[]>(
      '/api/system-config/scales',
      { signal }
    );
    return response.map(mapScaleConfigSummary);
  }

  async getScaleConfig(scaleId: string, signal?: AbortSignal) {
    return apiRequest<
      Awaited<ReturnType<CareRepository['getScaleConfig']>>
    >(`/api/system-config/scales/${encodeURIComponent(scaleId)}`, { signal });
  }

  async updateScaleConfig(
    scaleId: string,
    input: Parameters<CareRepository['updateScaleConfig']>[1],
    signal?: AbortSignal
  ) {
    return apiRequest<
      Awaited<ReturnType<CareRepository['updateScaleConfig']>>
    >(`/api/system-config/scales/${encodeURIComponent(scaleId)}`, {
      method: 'PUT',
      body: input,
      signal,
    });
  }

  async loginPatient(input: PatientLoginInput, signal?: AbortSignal) {
    const response = await apiRequest<PatientLoginResponse>(
      '/api/patients/login',
      {
        method: 'POST',
        body: {
          id_card_no: input.idCardNo,
          phone: input.phone,
        },
        signal,
      }
    );
    return mapPatientPortal(response);
  }

  async loginStaff(input: StaffLoginInput, signal?: AbortSignal) {
    const response = await apiRequest<StaffLoginResponse>(
      '/api/auth/staff/login',
      {
        method: 'POST',
        body: {
          staff_no: input.staffNo,
          password: input.password,
        },
        signal,
      }
    );
    return mapStaffUser(response);
  }

  async getCurrentStaff(signal?: AbortSignal) {
    const response = await apiRequest<StaffLoginResponse>(
      '/api/auth/staff/me',
      { signal }
    );
    return mapStaffUser(response);
  }

  async logoutStaff(signal?: AbortSignal) {
    await apiRequest<void>('/api/auth/staff/logout', {
      method: 'POST',
      signal,
    });
  }

  async listPatientTasks(signal?: AbortSignal) {
    const response = await apiRequest<BackendTaskDto[]>(
      '/api/patients/me/tasks',
      { signal }
    );
    return response.map(mapTaskDto);
  }

  async listMyTasks(signal?: AbortSignal) {
    const response = await apiRequest<BackendTaskDto[]>(
      '/api/tasks',
      { signal }
    );
    return response.map(mapTaskDto);
  }

  async createTask(input: CreateTaskInput, signal?: AbortSignal) {
    const response = await apiRequest<CreateTaskResponse>('/api/tasks', {
      method: 'POST',
      body: mapCreateTaskRequest({
        patient_id: input.patient.id,
        encounter_id: input.encounter.id,
        assigned_nurse_id: input.nurseId,
        scale_ids: input.scaleIds,
        collection_mode: input.collectionMode,
        participant_type: input.participantType,
        assessment_scene: input.assessmentScene,
        planned_start_time: input.plannedStartTime,
      }),
      signal,
    });
    return response.task
      ? mapTaskDto(response.task)
      : buildTaskFallback(input, response);
  }

  async getTask(taskId: string, signal?: AbortSignal) {
    const response = await apiRequest<BackendTaskDto>(
      `/api/tasks/${encodeURIComponent(taskId)}`,
      { signal }
    );
    return mapTaskDto(response);
  }

  async getNursingPlan(taskId: string, signal?: AbortSignal) {
    const response = await apiRequest<NursingPlanDto | null>(
      `/api/tasks/${encodeURIComponent(taskId)}/nursing-plan`,
      { signal }
    );
    return response ? mapNursingPlan(response) : null;
  }

  async generateNursingPlan(
    taskId: string,
    force = false,
    signal?: AbortSignal
  ) {
    const response = await apiRequest<NursingPlanDto>(
      `/api/tasks/${encodeURIComponent(taskId)}/nursing-plan/generate`,
      {
        method: 'POST',
        body: { force },
        signal,
        // 真实模型结构化生成通常需要几十秒，不能沿用普通接口的短超时。
        timeoutMs: 120_000,
      }
    );
    return mapNursingPlan(response);
  }

  async updateNursingPlan(
    taskId: string,
    input: NursingPlanUpdate,
    signal?: AbortSignal
  ) {
    const response = await apiRequest<NursingPlanDto>(
      `/api/tasks/${encodeURIComponent(taskId)}/nursing-plan`,
      {
        method: 'PUT',
        body: {
          risk_summary: input.riskSummary,
          education_summary: input.educationSummary,
          handover_summary: input.handoverSummary,
          items: input.items.map((item) => ({
            id: item.id,
            item_content: item.itemContent,
            priority: item.priority,
            nurse_action: item.nurseAction,
            nurse_comment: item.nurseComment ?? null,
          })),
        },
        signal,
      }
    );
    return mapNursingPlan(response);
  }

  async confirmNursingPlan(taskId: string, signal?: AbortSignal) {
    const response = await apiRequest<NursingPlanDto>(
      `/api/tasks/${encodeURIComponent(taskId)}/nursing-plan/confirm`,
      { method: 'POST', signal }
    );
    return mapNursingPlan(response);
  }

  async getDialogueSnapshot(task: CareTask, signal?: AbortSignal) {
    const sessionId = task.sessionId ?? task.id;
    const [history, extraction, events] = await Promise.all([
      apiRequest<DialogHistoryResponse>(
        `/api/dialog/${encodeURIComponent(sessionId)}/history?limit=100&offset=0`,
        { signal }
      ),
      apiRequest<ExtractedFieldsResponse>(
        `/api/extraction/${encodeURIComponent(sessionId)}/fields`,
        { signal }
      ),
      apiRequest<SseEnvelope[]>(
        `/api/dialog/${encodeURIComponent(sessionId)}/events`,
        { signal }
      ),
    ]);
    return {
      session: mapDialogHistory(history, task),
      answers: extraction.fields.map(mapExtractedField),
      events,
      manualIntervention: extraction.manual_intervention ?? false,
      interventionReason: extraction.intervention_reason,
    };
  }

  async updateManualField(
    sessionId: string,
    input: Parameters<CareRepository['updateManualField']>[1],
    signal?: AbortSignal
  ) {
    const response = await apiRequest<ExtractedFieldsResponse>(
      `/api/extraction/${encodeURIComponent(sessionId)}/fields/${encodeURIComponent(input.questionId)}`,
      {
        method: 'PUT',
        body: {
          question_id: Number(input.questionId),
          answer_type: input.answerType,
          answer_text: input.answerText ?? null,
          answer_number: input.answerNumber ?? null,
          answer_boolean: input.answerBoolean ?? null,
          answer_date: input.answerDate ?? null,
          selected_option_codes: input.selectedOptionCodes ?? [],
          complete_manual: input.completeManual ?? false,
        },
        signal,
      }
    );
    const task = useTaskStore.getState().tasks.find((item) => item.sessionId === sessionId);
    if (!task) throw new Error('任务不存在，无法刷新对话快照');
    return {
      session: mapDialogHistory(
        await apiRequest<DialogHistoryResponse>(
          `/api/dialog/${encodeURIComponent(sessionId)}/history?limit=100&offset=0`,
          { signal }
        ),
        task
      ),
      answers: response.fields.map(mapExtractedField),
      events: await apiRequest<SseEnvelope[]>(
        `/api/dialog/${encodeURIComponent(sessionId)}/events`,
        { signal }
      ),
      manualIntervention: response.manual_intervention ?? false,
      interventionReason: response.intervention_reason,
    };
  }

  async sendDialogMessage(
    input: Parameters<CareRepository['sendDialogMessage']>[0],
    signal?: AbortSignal
  ) {
    await apiRequest<void>('/api/dialog/message', {
      method: 'POST',
      body: {
        session_id: input.sessionId,
        task_id: input.taskId,
        content: input.content,
        client_message_id: input.clientMessageId,
        input_mode: input.inputMode ?? 'text',
      },
      signal,
    });
  }

  async saveQuestionnaireDraft(
    taskId: string,
    answers: Parameters<CareRepository['saveQuestionnaireDraft']>[1],
    signal?: AbortSignal
  ) {
    await apiRequest<void>(
      `/api/tasks/${encodeURIComponent(taskId)}/questionnaire/draft`,
      {
        method: 'PUT',
        body: { task_id: taskId, answers },
        signal,
      }
    );
  }

  async submitQuestionnaire(
    taskId: string,
    answers: Parameters<CareRepository['submitQuestionnaire']>[1],
    signal?: AbortSignal
  ) {
    await apiRequest<void>(
      `/api/tasks/${encodeURIComponent(taskId)}/questionnaire/submit`,
      {
        method: 'POST',
        body: { task_id: taskId, answers },
        signal,
      }
    );
  }

  async pauseDialogue(sessionId: string, signal?: AbortSignal) {
    await apiRequest<void>(
      `/api/dialog/${encodeURIComponent(sessionId)}/pause`,
      { method: 'POST', signal }
    );
  }

  async resumeDialogue(sessionId: string, signal?: AbortSignal) {
    await apiRequest<void>(
      `/api/dialog/${encodeURIComponent(sessionId)}/resume`,
      { method: 'POST', signal }
    );
  }

  async requestHandoff(
    taskId: string,
    reason: string,
    details?: {
      requestedAction?: string;
      urgency?: 'routine' | 'urgent';
      clientInvocationId?: string;
    },
    signal?: AbortSignal
  ) {
    return apiRequest<Record<string, unknown>>(
      `/api/tasks/${encodeURIComponent(taskId)}/handoff`,
      {
        method: 'POST',
        body: {
          task_id: taskId,
          reason,
          requested_action: details?.requestedAction ?? 'other',
          urgency: details?.urgency ?? 'routine',
          client_invocation_id: details?.clientInvocationId,
        },
        signal,
      }
    );
  }

  async resolveHandoff(
    taskId: string,
    requestId?: string,
    signal?: AbortSignal
  ) {
    return apiRequest<Record<string, unknown>>(
      `/api/tasks/${encodeURIComponent(taskId)}/handoff/resolve`,
      {
        method: 'POST',
        body: requestId ? { request_id: requestId } : {},
        signal,
      }
    );
  }

  async submitMessageFeedback(
    feedback: Parameters<CareRepository['submitMessageFeedback']>[0],
    signal?: AbortSignal
  ) {
    await apiRequest<void>('/api/rating', {
      method: 'POST',
      body: {
        task_id: feedback.taskId,
        message_id: feedback.messageId,
        reviewer_id: toReviewerId(feedback.reviewerId),
        rating: feedback.feedbackType,
        score: feedback.score,
        issue_tags: feedback.issueTags,
        comment: feedback.comment,
      },
      signal,
    });
  }

  async listMessageFeedback(
    taskId: string,
    reviewerId?: string,
    signal?: AbortSignal
  ) {
    const query = new URLSearchParams({
      task_id: taskId,
      reviewer_id: String(toReviewerId(reviewerId)),
    });
    const response = await apiRequest<MessageRatingListResponse>(
      `/api/rating?${query.toString()}`,
      { signal }
    );
    return response.items.map(mapMessageRating);
  }

  async submitConsent(
    consent: Parameters<CareRepository['submitConsent']>[0],
    signal?: AbortSignal
  ) {
    await apiRequest<void>(
      `/api/consent-forms/${encodeURIComponent(consent.taskId)}/sign`,
      {
        method: 'POST',
        body: {
          task_id: consent.taskId,
          form_id: consent.formId ?? '',
          document_version: consent.documentVersion,
          participant_name: consent.participantName,
          decision: consent.decision,
          signature_data: consent.signatureData,
          clauses: consent.clauses,
        },
        signal,
      }
    );
  }

  async acknowledgeEducation(
    taskId: string,
    eventId: string,
    materialId: string,
    signal?: AbortSignal
  ) {
    return apiRequest<Record<string, unknown>>(
      `/api/tasks/${encodeURIComponent(taskId)}/education/acknowledge`,
      {
        method: 'POST',
        body: {
          task_id: taskId,
          event_id: eventId,
          material_id: materialId,
        },
        signal,
      }
    );
  }

  async submitQualityReview(
    review: Parameters<CareRepository['submitQualityReview']>[0],
    signal?: AbortSignal
  ) {
    await apiRequest<void>('/api/quality-reviews', {
      method: 'POST',
      body: {
        task_id: review.taskId,
        reviewer_id: toReviewerId(review.reviewerId),
        dialogue_scores: review.dialogueScores,
        assessment_scores: review.assessmentScores,
        dialogue_comments: review.dialogueComments,
        assessment_comments: review.assessmentComments,
        evidence_message_ids: review.evidenceMessageIds,
        evidence_question_ids: review.evidenceQuestionIds,
        comment: review.comment,
      },
      signal,
    });
  }

  async getQualityReview(
    taskId: string,
    reviewerId?: string,
    signal?: AbortSignal
  ) {
    const query = new URLSearchParams({
      reviewer_id: String(toReviewerId(reviewerId)),
    });
    const response = await apiRequest<QualityReviewDto | null>(
      `/api/quality-reviews/${encodeURIComponent(taskId)}?${query.toString()}`,
      { signal }
    );
    return response ? mapQualityReview(response) : null;
  }

  async submitAssessmentReview(
    review: Parameters<CareRepository['submitAssessmentReview']>[0],
    signal?: AbortSignal
  ) {
    await apiRequest<void>(
      `/api/tasks/${encodeURIComponent(review.taskId)}/review`,
      {
        method: 'POST',
        body: {
          task_id: review.taskId,
          nurse_answers: review.nurseAnswers,
          final_answers: review.finalAnswers,
          correction_reasons: review.correctionReasons,
          supplementary_inquiry: review.supplementaryInquiry,
          status: review.status,
        },
        signal,
      }
    );
  }
}
