import {
  mockEncounters,
  mockPatients,
  mockScales,
  mockTasks,
} from '@/lib/mock/data';
import { getVisibleQuestions } from '@/lib/mock/assessment';
import type {
  AssessmentScaleConfigDetail,
  AssessmentScaleConfigSummary,
  CareTask,
  EducationMaterialConfig,
  InteractionRuleConfig,
  InteractionSession,
  NursingPlan,
  NursingPlanUpdate,
  QuestionnaireSnapshot,
  User,
} from '@/lib/types';
import type {
  CareRepository,
  CreateTaskInput,
  DialogueSnapshot,
  PatientListFilters,
  PatientLoginInput,
  PatientTaskVerifyInput,
  PatientNotification,
  WardGuide,
  PatientAssistantSession,
  ConsentSnapshot,
  PatientRecordInput,
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

const mockNursingPlans = new Map<string, NursingPlan>();

function buildMockNursingPlan(taskId: string): NursingPlan {
  const now = new Date().toISOString();
  return {
    id: 1,
    taskId: Number(taskId) || 1,
    planNo: `PLAN-DEMO-${taskId}`,
    planStatus: 'ai_draft',
    riskSummary: '当前为演示草案：建议重点关注跌倒风险、用药过敏信息和患者理解程度。',
    educationSummary: '用药前核对过敏史，采用短句和回教法确认患者理解。',
    handoverSummary: '交接班时说明患者配合度、认知状态及需要持续观察的风险点。',
    generatedBy: 'ai:demo',
    confirmedBy: null,
    confirmedAt: null,
    profile: {
      id: 1,
      profileNo: `PROFILE-DEMO-${taskId}`,
      sourceSubmissionIds: [1],
      cooperationLevel: 'partial',
      cognitionLevel: 'clear',
      selfCareLevel: 'partial_assistance',
      fallRiskLevel: 'medium',
      pressureRiskLevel: 'low',
      nutritionRiskLevel: 'medium',
      communicationLevel: 'good',
      educationNeedLevel: 'high',
      detail: {
        task_id: Number(taskId) || 1,
        summary: '患者可正常交流，但需要护士使用通俗语言并重复确认重点。',
        evidence: ['演示评估结果', '对话理解度观察'],
      },
      generatedBy: 'ai:demo',
      generatedAt: now,
    },
    items: [
      {
        id: 1,
        itemType: 'observation',
        itemCode: 'fall_risk_observation',
        itemContent: '首次下床及夜间活动时陪同，观察头晕、步态不稳等表现。',
        sourceType: 'assessment_score',
        sourceId: 'demo-fall-score',
        priority: 'high',
        nurseAction: 'pending',
        nurseComment: null,
      },
      {
        id: 2,
        itemType: 'education',
        itemCode: 'medication_allergy_education',
        itemContent: '用药前向患者复述过敏药物核对要点，并请患者回述。',
        sourceType: 'risk_event',
        sourceId: 'demo-allergy-event',
        priority: 'medium',
        nurseAction: 'pending',
        nurseComment: null,
      },
      {
        id: 3,
        itemType: 'nursing_measure',
        itemCode: 'nutrition_follow_up',
        itemContent: '观察进食量和食欲变化，必要时记录并反馈责任医生。',
        sourceType: 'assessment_answer',
        sourceId: 'demo-nutrition-answer',
        priority: 'low',
        nurseAction: 'pending',
        nurseComment: null,
      },
    ],
  };
}

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

function calculateAge(birthday: string): number {
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

function buildMockPatientRecord(
  patient: (typeof mockPatients)[number],
  encounter: (typeof mockEncounters)[number]
): PatientWithEncounter {
  const tasks = mockTasks.filter((task) => task.patientId === patient.id);
  return {
    patient: structuredClone(patient),
    encounter: structuredClone(encounter),
    taskSummary: {
      total: tasks.length,
      pendingReview: tasks.filter(
        (task) => task.taskStatus === 'pending_review'
      ).length,
      inProgress: tasks.filter(
        (task) => task.taskStatus === 'in_progress'
      ).length,
      handoffRequired: tasks.some((task) => task.handoffRequired),
    },
  };
}

function buildMockRecordFromInput(
  input: PatientRecordInput,
  patientId: string,
  encounterId: string,
  patientNo: string,
  encounterNo: string,
  maskedIdCard?: string
): PatientWithEncounter {
  const patient = {
    id: patientId,
    patientNo,
    hisPatientId: input.patient.hisPatientId,
    name: input.patient.name,
    gender: input.patient.gender,
    age: calculateAge(input.patient.birthday),
    birthday: input.patient.birthday,
    idCard: input.patient.idCardNo
      ? `${input.patient.idCardNo.slice(0, 3)}***********${input.patient.idCardNo.slice(-4)}`
      : maskedIdCard,
    phone: input.patient.phone,
    emergencyContactName: input.patient.emergencyContactName,
    emergencyContactRelation: input.patient.emergencyContactRelation,
    emergencyContactPhone: input.patient.emergencyContactPhone,
    address: input.patient.address,
  };
  const encounter = {
    id: encounterId,
    patientId,
    encounterNo,
    inpatientNo: input.encounter.inpatientNo,
    departmentCode: input.encounter.departmentCode,
    department: input.encounter.department,
    ward: input.encounter.ward,
    bedNo: input.encounter.bedNo,
    admissionDate: input.encounter.admissionDate,
    dischargeDate: input.encounter.dischargeDate,
    diagnosis: input.encounter.primaryDiagnosis,
    diagnosisSnapshot: {
      primary: input.encounter.primaryDiagnosis,
      secondary: input.encounter.secondaryDiagnoses,
      risk_note: input.encounter.riskNote ?? '',
    },
    encounterStatus: input.encounter.encounterStatus,
    admissionSource: input.encounter.admissionSource,
    nursingLevel: input.encounter.nursingLevel,
    insuranceType: input.encounter.insuranceType,
    allergySummary: input.encounter.allergySummary,
  };
  return { patient, encounter };
}

export class MockCareRepository implements CareRepository {
  async listPatients(
    filters: PatientListFilters = {},
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]> {
    await wait(signal);
    const normalizedKeyword = filters.keyword?.trim().toLowerCase() ?? '';
    const statusMap: Record<
      NonNullable<PatientListFilters['status']>,
      (typeof mockEncounters)[number]['encounterStatus'] | ''
    > = {
      '': '',
      待入院: 'pending_admission',
      在院: 'in_hospital',
      已出院: 'discharged',
      取消: 'cancelled',
    };
    return mockPatients.flatMap((patient) => {
      const encounter = mockEncounters.find(
        (item) => item.patientId === patient.id
      );
      if (!encounter) return [];
      const searchable = [
        patient.name,
        patient.patientNo,
        patient.hisPatientId,
        encounter.inpatientNo,
        encounter.bedNo,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      const expectedStatus = statusMap[filters.status ?? ''];
      if (normalizedKeyword && !searchable.includes(normalizedKeyword)) {
        return [];
      }
      if (expectedStatus && encounter.encounterStatus !== expectedStatus) {
        return [];
      }
      if (
        filters.departmentName &&
        encounter.department !== filters.departmentName
      ) {
        return [];
      }
      if (filters.wardName && encounter.ward !== filters.wardName) {
        return [];
      }
      return [buildMockPatientRecord(patient, encounter)];
    });
  }

  async listInHospitalPatients(
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]> {
    return this.listPatients({ status: '在院' }, signal);
  }

  async getPatient(
    patientId: string,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter> {
    await wait(signal);
    const patient = mockPatients.find((item) => item.id === patientId);
    const encounter = mockEncounters.find(
      (item) => item.patientId === patientId
    );
    if (!patient || !encounter) throw new Error('患者住院记录不存在');
    return buildMockPatientRecord(patient, encounter);
  }

  async createPatient(
    input: PatientRecordInput,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter> {
    await wait(signal);
    if (
      mockEncounters.some(
        (item) => item.inpatientNo === input.encounter.inpatientNo
      )
    ) {
      throw new Error('住院号已存在');
    }
    const sequence = String(Date.now()).slice(-8);
    const record = buildMockRecordFromInput(
      input,
      `P-${sequence}`,
      `E-${sequence}`,
      `P2026${sequence}`,
      `E2026${sequence}`
    );
    mockPatients.push(record.patient);
    mockEncounters.push(record.encounter);
    return buildMockPatientRecord(record.patient, record.encounter);
  }

  async updatePatient(
    patientId: string,
    input: PatientRecordInput,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter> {
    await wait(signal);
    const patientIndex = mockPatients.findIndex((item) => item.id === patientId);
    const encounterIndex = mockEncounters.findIndex(
      (item) =>
        item.patientId === patientId &&
        (!input.encounter.id || item.id === input.encounter.id)
    );
    if (patientIndex < 0 || encounterIndex < 0) {
      throw new Error('患者住院记录不存在');
    }
    if (
      mockEncounters.some(
        (item, index) =>
          index !== encounterIndex &&
          item.inpatientNo === input.encounter.inpatientNo
      )
    ) {
      throw new Error('住院号已存在');
    }
    const currentPatient = mockPatients[patientIndex];
    const currentEncounter = mockEncounters[encounterIndex];
    const record = buildMockRecordFromInput(
      input,
      currentPatient.id,
      currentEncounter.id,
      currentPatient.patientNo,
      currentEncounter.encounterNo,
      currentPatient.idCard
    );
    mockPatients[patientIndex] = record.patient;
    mockEncounters[encounterIndex] = record.encounter;
    return buildMockPatientRecord(record.patient, record.encounter);
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

  async verifyPatientTask(
    _input: PatientTaskVerifyInput,
    signal?: AbortSignal
  ) {
    await wait(signal);
    return {
      patient: mockPatients[0],
      encounter: mockEncounters[0],
      tasks: mockTasks.filter((task) => task.patientId === mockPatients[0].id),
    };
  }

  async verifyPatientScanToken(_token: string, signal?: AbortSignal) {
    await wait(signal);
    return {
      patient: mockPatients[0],
      encounter: mockEncounters[0],
      tasks: mockTasks.filter((task) => task.patientId === mockPatients[0].id),
    };
  }

  async listPatientNotifications(
    _unreadOnly = false,
    signal?: AbortSignal
  ): Promise<{ items: PatientNotification[]; unreadCount: number }> {
    void _unreadOnly;
    await wait(signal);
    return { items: [], unreadCount: 0 };
  }

  async markPatientNotificationRead(
    notificationId: string,
    signal?: AbortSignal
  ): Promise<PatientNotification> {
    await wait(signal);
    return {
      id: notificationId,
      notificationNo: notificationId,
      notificationType: 'general',
      title: '',
      content: '',
      priority: 'normal',
      payload: {},
      readAt: new Date().toISOString(),
      createdAt: new Date().toISOString(),
    };
  }

  async listPatientWardGuide(signal?: AbortSignal): Promise<WardGuide[]> {
    await wait(signal);
    return [];
  }

  async createPatientAssistantSession(
    channelType: 'text' | 'voice' = 'text',
    signal?: AbortSignal
  ): Promise<PatientAssistantSession> {
    await wait(signal);
    return {
      sessionNo: `MOCK-ASSISTANT-${Date.now()}`,
      channelType,
      sessionStatus: 'active',
      handoffRequired: false,
      messages: [],
    };
  }

  async getPatientAssistantSession(
    sessionNo: string,
    signal?: AbortSignal
  ): Promise<PatientAssistantSession> {
    await wait(signal);
    return {
      sessionNo,
      channelType: 'text',
      sessionStatus: 'active',
      handoffRequired: false,
      messages: [],
    };
  }

  async sendPatientAssistantMessage(
    sessionNo: string,
    content: string,
    _clientMessageId?: string,
    signal?: AbortSignal
  ): Promise<PatientAssistantSession> {
    await wait(signal);
    return {
      sessionNo,
      channelType: 'text',
      sessionStatus: 'active',
      handoffRequired: false,
      messages: [
        {
          messageNo: `MOCK-${Date.now()}-P`,
          role: 'patient',
          content,
          occurredAt: new Date().toISOString(),
        },
        {
          messageNo: `MOCK-${Date.now()}-A`,
          role: 'assistant',
          content: '请以病区实际通知为准，如需帮助请联系护士。',
          resultStatus: 'handoff_required',
          occurredAt: new Date().toISOString(),
        },
      ],
    };
  }

  async getConsentSnapshot(
    taskId: string,
    signal?: AbortSignal
  ): Promise<ConsentSnapshot> {
    await wait(signal);
    throw new Error(`Mock任务 ${taskId} 使用页面内置知情同意演示`);
  }

  async recordConsentPlayback(
    _taskId: string,
    _input: Parameters<CareRepository['recordConsentPlayback']>[1],
    signal?: AbortSignal
  ) {
    await wait(signal);
    return { status: 'mock' };
  }

  async confirmConsentClause(
    _taskId: string,
    _clauseId: number,
    _input: Parameters<CareRepository['confirmConsentClause']>[2],
    signal?: AbortSignal
  ) {
    await wait(signal);
    return { status: 'mock' };
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

  async retryTaskPreparation(
    taskId: string,
    signal?: AbortSignal
  ): Promise<CareTask> {
    await wait(signal);
    const task = mockTasks.find((item) => item.id === taskId);
    if (!task) throw new Error(`Mock任务 ${taskId} 不存在`);
    return structuredClone(task);
  }

  async getNursingPlan(taskId: string, signal?: AbortSignal) {
    await wait(signal);
    const current = mockNursingPlans.get(taskId);
    return structuredClone(current ?? null);
  }

  async generateNursingPlan(
    taskId: string,
    force = false,
    signal?: AbortSignal
  ) {
    await wait(signal);
    if (!force && mockNursingPlans.has(taskId)) {
      return structuredClone(mockNursingPlans.get(taskId) as NursingPlan);
    }
    const plan = buildMockNursingPlan(taskId);
    mockNursingPlans.set(taskId, plan);
    return structuredClone(plan);
  }

  async updateNursingPlan(
    taskId: string,
    input: NursingPlanUpdate,
    signal?: AbortSignal
  ) {
    await wait(signal);
    const current =
      mockNursingPlans.get(taskId) ?? buildMockNursingPlan(taskId);
    const updated: NursingPlan = {
      ...current,
      planStatus: 'adjusted',
      riskSummary: input.riskSummary,
      educationSummary: input.educationSummary,
      handoverSummary: input.handoverSummary,
      items: current.items.map((item) => {
        const next = input.items.find((candidate) => candidate.id === item.id);
        return next
          ? {
              ...item,
              itemContent: next.itemContent,
              priority: next.priority,
              nurseAction: next.nurseAction,
              nurseComment: next.nurseComment ?? null,
            }
          : item;
      }),
    };
    mockNursingPlans.set(taskId, updated);
    return structuredClone(updated);
  }

  async confirmNursingPlan(taskId: string, signal?: AbortSignal) {
    await wait(signal);
    const current =
      mockNursingPlans.get(taskId) ?? buildMockNursingPlan(taskId);
    if (current.items.some((item) => item.nurseAction === 'pending')) {
      throw new Error('请先处理全部护理计划明细');
    }
    if (current.items.every((item) => item.nurseAction === 'rejected')) {
      throw new Error('护理计划至少需要保留一条有效建议');
    }
    const confirmed: NursingPlan = {
      ...current,
      planStatus: 'confirmed',
      confirmedBy: 1,
      confirmedAt: new Date().toISOString(),
    };
    mockNursingPlans.set(taskId, confirmed);
    return structuredClone(confirmed);
  }

  async getDialogueSnapshot(
    task: CareTask,
    signal?: AbortSignal
  ): Promise<DialogueSnapshot> {
    await wait(signal);
    return { session: buildEmptySession(task), answers: [], events: [] };
  }

  async updateManualField(
    _sessionId: string,
    _input: Parameters<CareRepository['updateManualField']>[1],
    signal?: AbortSignal
  ): Promise<DialogueSnapshot> {
    await wait(signal);
    return { session: buildEmptySession({ id: _sessionId } as CareTask), answers: [], events: [] };
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

  async getQuestionnaire(
    taskId: string,
    signal?: AbortSignal
  ): Promise<QuestionnaireSnapshot> {
    await wait(signal);
    const task = mockTasks.find((item) => item.id === taskId);
    const questions = getVisibleQuestions({}, task?.scaleIds);
    return {
      taskId,
      taskNo: task?.taskNo ?? taskId,
      status: task?.taskStatus === 'completed' ? 'confirmed' : 'not_started',
      questions,
      answers: [],
      answerValues: {},
      scores: [],
    };
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
      clientInvocationId?: string;
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
