import {
  mockEncounters,
  mockPatients,
  mockScales,
  mockTasks,
} from '@/lib/mock/data';
import type { CareTask, InteractionSession, User } from '@/lib/types';
import type {
  CareRepository,
  CreateTaskInput,
  DialogueSnapshot,
  PatientLoginInput,
  PatientWithEncounter,
  SendMessageInput,
  StaffLoginInput,
} from '@/lib/repositories/types';

const MOCK_DELAY_MS = 180;

const MOCK_STAFF_USERS: Record<
  string,
  { password: string; user: User }
> = {
  N001: {
    password: '123456',
    user: {
      id: 'N001',
      username: 'N001',
      role: 'nurse',
      name: '李护士',
      department: '心内科',
      avatar: '',
    },
  },
  N002: {
    password: '123456',
    user: {
      id: 'N002',
      username: 'N002',
      role: 'nurse',
      name: '王护士',
      department: '老年医学科',
      avatar: '',
    },
  },
  N003: {
    password: '123456',
    user: {
      id: 'N003',
      username: 'N003',
      role: 'nurse',
      name: '赵护士',
      department: '消化内科',
      avatar: '',
    },
  },
  N004: {
    password: '123456',
    user: {
      id: 'N004',
      username: 'N004',
      role: 'nurse',
      name: '陈护士',
      department: '呼吸与危重症医学科',
      avatar: '',
    },
  },
  N005: {
    password: '123456',
    user: {
      id: 'N005',
      username: 'N005',
      role: 'nurse',
      name: '刘护士',
      department: '骨科',
      avatar: '',
    },
  },
};

function wait(signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = globalThis.setTimeout(resolve, MOCK_DELAY_MS);
    const abort = () => {
      globalThis.clearTimeout(timeout);
      reject(new DOMException('请求已取消', 'AbortError'));
    };
    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener('abort', abort, { once: true });
  });
}

function buildMockTask(input: CreateTaskInput): CareTask {
  const timestamp = Date.now();
  const id = `T-${timestamp}`;
  return {
    id,
    taskNo: `TASK-${String(timestamp).slice(-8)}`,
    sessionId: `SESSION-${id}`,
    patientId: input.patient.id,
    encounterId: input.encounter.id,
    encounterNo: input.encounter.inpatientNo,
    patientName: input.patient.name,
    bedNo: input.encounter.bedNo,
    department: input.encounter.department,
    wardName: input.encounter.ward,
    taskType: '入院评估任务包',
    collectionMode: input.collectionMode,
    taskStatus: 'pending',
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
    progress: { current: 0, total: 12 },
  };
}

function buildEmptySession(task: CareTask): InteractionSession {
  const sessionId = task.sessionId ?? `SESSION-${task.id}`;
  return {
    id: sessionId,
    sessionNo: sessionId,
    taskId: task.id,
    patientId: task.patientId,
    encounterId: task.encounterId,
    interactionType: 'assessment',
    channelType: 'mixed',
    sessionStatus: 'active',
    startedAt: new Date().toISOString(),
    currentCicareStage: 'connect',
    answeredQuestionCount: 0,
    totalQuestionCount: task.progress?.total ?? 7,
    messages: [],
  };
}

export class MockCareRepository implements CareRepository {
  async listInHospitalPatients(
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]> {
    await wait(signal);
    return mockPatients.flatMap((patient) => {
      const encounter = mockEncounters.find(
        (item) => item.patientId === patient.id
      );
      return encounter ? [{ patient, encounter }] : [];
    });
  }

  async listScales(signal?: AbortSignal) {
    await wait(signal);
    return mockScales;
  }

  async loginPatient(_input: PatientLoginInput, signal?: AbortSignal) {
    await wait(signal);
    return {
      patient: mockPatients[0],
      encounter: mockEncounters[0],
      tasks: mockTasks.filter((task) => task.patientId === mockPatients[0].id),
    };
  }

  async loginStaff(input: StaffLoginInput, signal?: AbortSignal) {
    await wait(signal);
    const account = MOCK_STAFF_USERS[input.staffNo.trim().toUpperCase()];
    if (!account || account.password !== input.password) {
      throw new Error('工号或密码错误');
    }
    return account.user;
  }

  async getCurrentStaff(signal?: AbortSignal) {
    await wait(signal);
    return MOCK_STAFF_USERS.N001.user;
  }

  async logoutStaff(signal?: AbortSignal) {
    await wait(signal);
  }

  async listMyTasks(signal?: AbortSignal) {
    await wait(signal);
    return mockTasks;
  }

  async createTask(input: CreateTaskInput, signal?: AbortSignal) {
    await wait(signal);
    return buildMockTask(input);
  }

  async getTask(
    taskId: string,
    signal?: AbortSignal
  ): Promise<CareTask> {
    await wait(signal);
    throw new Error(`Mock任务 ${taskId} 应从本地Store读取`);
  }

  async getDialogueSnapshot(
    task: CareTask,
    signal?: AbortSignal
  ): Promise<DialogueSnapshot> {
    await wait(signal);
    return { session: buildEmptySession(task), answers: [], events: [] };
  }

  async sendDialogMessage(
    _input: SendMessageInput,
    signal?: AbortSignal
  ): Promise<void> {
    await wait(signal);
  }

  async saveQuestionnaireDraft(
    _taskId: string,
    _answers: Parameters<CareRepository['saveQuestionnaireDraft']>[1],
    signal?: AbortSignal
  ) {
    await wait(signal);
  }

  async submitQuestionnaire(
    _taskId: string,
    _answers: Parameters<CareRepository['submitQuestionnaire']>[1],
    signal?: AbortSignal
  ) {
    await wait(signal);
  }

  async pauseDialogue(_sessionId: string, signal?: AbortSignal) {
    await wait(signal);
  }

  async resumeDialogue(_sessionId: string, signal?: AbortSignal) {
    await wait(signal);
  }

  async requestHandoff(
    _taskId: string,
    _reason: string,
    _details?: {
      requestedAction?: string;
      urgency?: 'routine' | 'urgent';
    },
    signal?: AbortSignal
  ) {
    await wait(signal);
    return {
      event_id: `HANDOFF-${Date.now()}`,
      event_type: 'handoff_requested',
      task_id: _taskId,
      request_id: `NURSE-${Date.now()}`,
      reason: _reason,
      requested_action: _details?.requestedAction ?? 'other',
      action_label: '人工护理协助',
      urgency: _details?.urgency ?? 'routine',
      request_source: 'patient',
      status: 'requested',
      timestamp: new Date().toISOString(),
    };
  }

  async resolveHandoff(
    _taskId: string,
    _requestId?: string,
    signal?: AbortSignal
  ) {
    await wait(signal);
    return {
      event_id: `HANDOFF-RESOLVED-${Date.now()}`,
      event_type: 'handoff_resolved',
      task_id: _taskId,
      request_id: _requestId,
      request_ids: _requestId ? [_requestId] : [],
      status: 'resolved',
      resolved_by_name: '演示护士',
      handled_at: new Date().toISOString(),
      remaining_pending: false,
      timestamp: new Date().toISOString(),
    };
  }

  async submitMessageFeedback(
    _feedback: Parameters<CareRepository['submitMessageFeedback']>[0],
    signal?: AbortSignal
  ) {
    await wait(signal);
  }

  async listMessageFeedback(
    _taskId: string,
    _reviewerId?: string,
    signal?: AbortSignal
  ) {
    await wait(signal);
    return [];
  }

  async submitConsent(
    _consent: Parameters<CareRepository['submitConsent']>[0],
    signal?: AbortSignal
  ) {
    await wait(signal);
  }

  async acknowledgeEducation(
    _taskId: string,
    _eventId: string,
    _materialId: string,
    signal?: AbortSignal
  ) {
    await wait(signal);
    return {
      event_id: `EDUCATION-STATUS-${Date.now()}`,
      event_type: 'education_status_updated',
      task_id: _taskId,
      source_event_id: _eventId,
      material_id: _materialId,
      status: 'acknowledged',
      acknowledged: true,
      acknowledged_at: new Date().toISOString(),
    };
  }

  async submitQualityReview(
    _review: Parameters<CareRepository['submitQualityReview']>[0],
    signal?: AbortSignal
  ) {
    await wait(signal);
  }

  async getQualityReview(
    _taskId: string,
    _reviewerId?: string,
    signal?: AbortSignal
  ) {
    await wait(signal);
    return null;
  }

  async submitAssessmentReview(
    _review: Parameters<CareRepository['submitAssessmentReview']>[0],
    signal?: AbortSignal
  ) {
    await wait(signal);
  }
}
