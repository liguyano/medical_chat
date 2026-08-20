import {
  mockEncounters,
  mockPatients,
  mockScales,
  mockTasks,
} from '@/lib/mock/data';
import type {
  AssessmentScaleConfigDetail,
  AssessmentScaleConfigSummary,
  CareTask,
  EducationMaterialConfig,
  InteractionRuleConfig,
  InteractionSession,
  User,
} from '@/lib/types';
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

const mockEducationMaterials: EducationMaterialConfig[] = [
  {
    id: '1',
    versionId: '1',
    unitId: '1',
    category: 'tobacco',
    title: '住院期间戒烟与烟草危害宣教',
    documentVersion: '1.0',
    originalContent: '吸烟会增加心脑血管和呼吸系统疾病风险，住院病区属于无烟环境。',
    patientContent: '住院期间请不要吸烟，如烟瘾明显请告诉护士。',
    spokenContent: '跟您提醒一下，住院期间请不要吸烟，如有不适请及时告诉护士。',
    sourceName: '系统内置演示材料',
    priority: 'medium',
    requiresAcknowledgement: true,
    autoPlay: true,
    enabled: true,
  },
  {
    id: '2',
    versionId: '2',
    unitId: '2',
    category: 'allergy',
    title: '药物过敏安全宣教',
    documentVersion: '1.0',
    originalContent: '已知或疑似药物过敏者，应主动说明具体药物及既往反应。',
    patientContent: '每次用药前，请主动告诉医生和护士您对什么药过敏。',
    spokenContent: '请记住，每次用药前都要主动说明具体对什么药过敏。',
    sourceName: '系统内置演示材料',
    priority: 'high',
    requiresAcknowledgement: true,
    autoPlay: true,
    enabled: true,
  },
];

const mockInteractionRules: InteractionRuleConfig[] = [
  {
    id: '1',
    ruleCode: 'allergy_risk',
    ruleName: '药物过敏特征',
    scopeType: 'global',
    keywords: ['过敏', '青霉素'],
    patterns: ['对.+过敏'],
    actionType: 'constraint_prompt',
    prompt: '追问具体过敏药物和既往反应，并调用药物过敏宣教材料。',
    tags: ['过敏', '高风险'],
    priority: 100,
    enabled: true,
  },
  {
    id: '2',
    ruleCode: 'smoking_risk',
    ruleName: '吸烟特征',
    scopeType: 'global',
    keywords: ['吸烟', '抽烟'],
    patterns: ['每天.*支'],
    actionType: 'constraint_prompt',
    prompt: '追问吸烟量和年限，并调用戒烟宣教材料。',
    tags: ['烟草'],
    priority: 60,
    enabled: true,
  },
];

const mockScaleSummaries: AssessmentScaleConfigSummary[] = mockScales.map(
  (scale) => ({
    id: scale.id,
    scaleCode: scale.scaleCode,
    scaleName: scale.scaleName,
    scaleType: scale.scaleType,
    clinicalPurpose: scale.description,
    status: 'published',
    versionId: scale.id,
    versionCode: '1.0',
    versionName: '演示版本',
    publishStatus: 'published',
    sectionCount: 1,
    questionCount: 3,
    optionCount: 6,
    ruleCount: 1,
    actionCount: 1,
  })
);

const mockScaleDetails: AssessmentScaleConfigDetail[] = mockScales.map(
  (scale, index) => ({
    id: Number(scale.id),
    scale_code: scale.scaleCode,
    scale_name: scale.scaleName,
    scale_type: scale.scaleType,
    clinical_purpose: scale.description,
    applicable_scope: { departments: ['全院'] },
    source_file: 'Demo 内置量表',
    status: 'published',
    version_id: Number(scale.id),
    version_code: '1.0',
    version_name: '演示版本',
    publish_status: 'published',
    scale_snapshot: {},
    sections: [
      {
        id: index * 100 + 1,
        parent_section_id: null,
        section_code: `${scale.scaleCode}_MAIN`,
        section_name: '主要评估项',
        section_description: scale.description,
        display_condition: null,
        sort_no: 1,
      },
    ],
    questions: [],
    options: [],
    rules: [],
    actions: [],
  })
);

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

  async listEducationMaterials(signal?: AbortSignal) {
    await wait(signal);
    return structuredClone(mockEducationMaterials);
  }

  async updateEducationMaterial(
    materialId: string,
    input: Parameters<CareRepository['updateEducationMaterial']>[1],
    signal?: AbortSignal
  ) {
    await wait(signal);
    const index = mockEducationMaterials.findIndex(
      (item) => item.id === materialId
    );
    if (index < 0) throw new Error('宣教材料不存在');
    mockEducationMaterials[index] = {
      ...mockEducationMaterials[index],
      ...input,
    };
    return structuredClone(mockEducationMaterials[index]);
  }

  async listInteractionRules(signal?: AbortSignal) {
    await wait(signal);
    return structuredClone(mockInteractionRules);
  }

  async updateInteractionRule(
    ruleId: string,
    input: Parameters<CareRepository['updateInteractionRule']>[1],
    signal?: AbortSignal
  ) {
    await wait(signal);
    const index = mockInteractionRules.findIndex((item) => item.id === ruleId);
    if (index < 0) throw new Error('拦截规则不存在');
    mockInteractionRules[index] = {
      ...mockInteractionRules[index],
      ...input,
    };
    return structuredClone(mockInteractionRules[index]);
  }

  async testInteractionRules(text: string, signal?: AbortSignal) {
    await wait(signal);
    return mockInteractionRules
      .filter((rule) => rule.enabled)
      .flatMap((rule) => {
        const matchedTerms = [
          ...rule.keywords.filter((keyword) => text.includes(keyword)),
          ...rule.patterns.flatMap((pattern) => {
            try {
              return text.match(new RegExp(pattern))?.slice(0, 1) ?? [];
            } catch {
              return [];
            }
          }),
        ];
        return matchedTerms.length
          ? [
              {
                ruleCode: rule.ruleCode,
                ruleName: rule.ruleName,
                matchedTerms,
                actionType: rule.actionType,
                prompt: rule.prompt,
                priority: rule.priority,
              },
            ]
          : [];
      })
      .sort((left, right) => right.priority - left.priority);
  }

  async listScaleConfigs(signal?: AbortSignal) {
    await wait(signal);
    return structuredClone(mockScaleSummaries);
  }

  async getScaleConfig(scaleId: string, signal?: AbortSignal) {
    await wait(signal);
    const detail = mockScaleDetails.find(
      (item) => String(item.id) === scaleId
    );
    if (!detail) throw new Error('评估量表不存在');
    return structuredClone(detail);
  }

  async updateScaleConfig(
    scaleId: string,
    input: Parameters<CareRepository['updateScaleConfig']>[1],
    signal?: AbortSignal
  ) {
    await wait(signal);
    const index = mockScaleDetails.findIndex(
      (item) => String(item.id) === scaleId
    );
    if (index < 0) throw new Error('评估量表不存在');
    mockScaleDetails[index] = structuredClone(input);
    return structuredClone(mockScaleDetails[index]);
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

  async listPatientTasks(signal?: AbortSignal) {
    await wait(signal);
    return mockTasks;
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
