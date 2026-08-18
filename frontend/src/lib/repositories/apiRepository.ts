import type {
  AssessmentScaleDto,
  BackendTaskDto,
  CreateTaskResponse,
  DialogHistoryResponse,
  ExtractedFieldsResponse,
  InHospitalPatientDto,
  MessageRatingListResponse,
  PatientLoginResponse,
  QualityReviewDto,
} from '@/lib/api/contracts';
import { apiRequest } from '@/lib/api/httpClient';
import {
  mapCreateTaskRequest,
  mapAssessmentScale,
  mapDialogHistory,
  mapExtractedField,
  mapInHospitalPatient,
  mapMessageRating,
  mapPatientPortal,
  mapQualityReview,
  mapTaskDto,
  toReviewerId,
} from '@/lib/api/mappers';
import type { AssessmentScale, CareTask } from '@/lib/types';
import type {
  CareRepository,
  CreateTaskInput,
  PatientLoginInput,
  PatientWithEncounter,
} from '@/lib/repositories/types';

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
  async listInHospitalPatients(
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]> {
    const response = await apiRequest<InHospitalPatientDto[]>(
      '/api/patients/in-hospital',
      { signal }
    );
    return response.map(mapInHospitalPatient);
  }

  async listScales(signal?: AbortSignal): Promise<AssessmentScale[]> {
    const response = await apiRequest<AssessmentScaleDto[]>('/api/scales', {
      signal,
    });
    return response.map(mapAssessmentScale);
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

  async listMyTasks(signal?: AbortSignal) {
    const response = await apiRequest<BackendTaskDto[]>(
      '/api/patients/me/tasks',
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

  async getDialogueSnapshot(task: CareTask, signal?: AbortSignal) {
    const sessionId = task.sessionId ?? task.id;
    const [history, extraction] = await Promise.all([
      apiRequest<DialogHistoryResponse>(
        `/api/dialog/${encodeURIComponent(sessionId)}/history?limit=100&offset=0`,
        { signal }
      ),
      apiRequest<ExtractedFieldsResponse>(
        `/api/extraction/${encodeURIComponent(sessionId)}/fields`,
        { signal }
      ),
    ]);
    return {
      session: mapDialogHistory(history, task),
      answers: extraction.fields.map(mapExtractedField),
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
    signal?: AbortSignal
  ) {
    await apiRequest<void>(`/api/tasks/${encodeURIComponent(taskId)}/handoff`, {
      method: 'POST',
      body: { task_id: taskId, reason },
      signal,
    });
  }

  async resolveHandoff(taskId: string, signal?: AbortSignal) {
    await apiRequest<void>(
      `/api/tasks/${encodeURIComponent(taskId)}/handoff/resolve`,
      { method: 'POST', signal }
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
          participant_name: consent.participantName,
          decision: consent.decision,
          signature_data: consent.signatureData,
          clauses: consent.clauses,
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
