import type {
  SseEnvelope,
} from '@/lib/api/contracts';
import type {
  AssessmentScale,
  CareTask,
  ConsentProgress,
  InteractionSession,
  MessageFeedback,
  Patient,
  PatientEncounter,
  QualityReview,
  PrototypeAnswerValue,
  StructuredAnswer,
  AssessmentReview,
  AssessmentScaleConfigDetail,
  AssessmentScaleConfigSummary,
  EducationMaterialConfig,
  EducationMaterialUpdate,
  InteractionRuleConfig,
  InteractionRuleMatch,
  InteractionRuleUpdate,
  NursingPlan,
  NursingPlanUpdate,
  QuestionnaireSnapshot,
  User,
} from '@/lib/types';

export interface PatientWithEncounter {
  patient: Patient;
  encounter: PatientEncounter;
  taskSummary?: PatientTaskSummary;
}

export interface PatientTaskSummary {
  total: number;
  pendingReview: number;
  inProgress: number;
  handoffRequired: boolean;
}

export interface PatientListFilters {
  keyword?: string;
  status?: '待入院' | '在院' | '已出院' | '取消' | '';
  departmentName?: string;
  wardName?: string;
}

export interface PatientRecordInput {
  patient: {
    hisPatientId?: string;
    name: string;
    gender: Patient['gender'];
    birthday: string;
    idCardNo?: string;
    phone: string;
    emergencyContactName?: string;
    emergencyContactRelation?: string;
    emergencyContactPhone?: string;
    address?: string;
  };
  encounter: {
    id?: string;
    inpatientNo: string;
    departmentCode?: string;
    department: string;
    ward: string;
    bedNo: string;
    admissionDate: string;
    dischargeDate?: string;
    encounterStatus: PatientEncounter['encounterStatus'];
    primaryDiagnosis: string;
    secondaryDiagnoses: string[];
    riskNote?: string;
    admissionSource?: string;
    nursingLevel?: string;
    insuranceType?: string;
    allergySummary?: string;
  };
}

export interface PatientLoginInput {
  idCardNo: string;
  phone: string;
}

export interface PatientTaskVerifyInput {
  taskNo: string;
  idCardSuffix: string;
}

export interface PatientNotification {
  id: string;
  notificationNo: string;
  notificationType: string;
  title: string;
  content: string;
  priority: string;
  payload: Record<string, unknown>;
  readAt?: string;
  createdAt: string;
}

export interface WardGuide {
  id: string;
  guideCode: string;
  category: string;
  title: string;
  content: string;
  departmentName?: string;
  wardName?: string;
  sortNo: number;
}

export interface PatientAssistantMessage {
  messageNo: string;
  role: 'patient' | 'assistant' | 'system';
  content: string;
  resultStatus?: string;
  sourceGuideId?: string;
  occurredAt: string;
}

export interface PatientAssistantSession {
  sessionNo: string;
  channelType: string;
  sessionStatus: string;
  handoffRequired: boolean;
  handoffReason?: string;
  messages: PatientAssistantMessage[];
}

export interface ConsentSnapshot {
  taskNo: string;
  recordId: number;
  consentCode: string;
  consentName: string;
  consentType: string;
  documentVersion: string;
  fullText: string;
  recordStatus: string;
  patientConfirmed: boolean;
  participantType: string;
  clauses: Array<Record<string, unknown>>;
  confirmations: Array<Record<string, unknown>>;
  playback: Array<Record<string, unknown>>;
  participants: Array<Record<string, unknown>>;
  signatures: Array<Record<string, unknown>>;
}

export interface StaffLoginInput {
  staffNo: string;
  password: string;
}

export interface PatientPortal {
  patient: Patient;
  encounter: PatientEncounter;
  tasks: CareTask[];
}

export interface CreateTaskInput {
  patient: Patient;
  encounter: PatientEncounter;
  nurseId: string;
  nurseName: string;
  scaleIds: string[];
  scaleNames: string[];
  collectionMode: CareTask['collectionMode'];
  participantType: NonNullable<CareTask['participantType']>;
  participantName: string;
  relationshipToPatient?: string;
  assessmentScene: NonNullable<CareTask['assessmentScene']>;
  consentRequired: boolean;
  educationTopics: string[];
  plannedStartTime?: string;
  notes?: string;
}

export interface DialogueSnapshot {
  session: InteractionSession;
  answers: StructuredAnswer[];
  events: SseEnvelope[];
  manualIntervention?: boolean;
  interventionReason?: string;
}

export interface ManualFieldUpdateInput {
  questionId: string;
  answerType: NonNullable<StructuredAnswer['answerType']>;
  answerText?: string;
  answerNumber?: number;
  answerBoolean?: boolean;
  answerDate?: string;
  selectedOptionCodes?: string[];
  completeManual?: boolean;
}

export interface SendMessageInput {
  taskId: string;
  sessionId: string;
  content: string;
  clientMessageId: string;
  inputMode?: 'text' | 'voice';
}

export interface CareRepository {
  listPatients(
    filters?: PatientListFilters,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter[]>;
  listInHospitalPatients(signal?: AbortSignal): Promise<PatientWithEncounter[]>;
  getPatient(
    patientId: string,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter>;
  createPatient(
    input: PatientRecordInput,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter>;
  updatePatient(
    patientId: string,
    input: PatientRecordInput,
    signal?: AbortSignal
  ): Promise<PatientWithEncounter>;
  listScales(signal?: AbortSignal): Promise<AssessmentScale[]>;
  listEducationMaterials(
    signal?: AbortSignal
  ): Promise<EducationMaterialConfig[]>;
  updateEducationMaterial(
    materialId: string,
    input: EducationMaterialUpdate,
    signal?: AbortSignal
  ): Promise<EducationMaterialConfig>;
  listInteractionRules(signal?: AbortSignal): Promise<InteractionRuleConfig[]>;
  updateInteractionRule(
    ruleId: string,
    input: InteractionRuleUpdate,
    signal?: AbortSignal
  ): Promise<InteractionRuleConfig>;
  testInteractionRules(
    text: string,
    signal?: AbortSignal
  ): Promise<InteractionRuleMatch[]>;
  listScaleConfigs(
    signal?: AbortSignal
  ): Promise<AssessmentScaleConfigSummary[]>;
  getScaleConfig(
    scaleId: string,
    signal?: AbortSignal
  ): Promise<AssessmentScaleConfigDetail>;
  updateScaleConfig(
    scaleId: string,
    input: AssessmentScaleConfigDetail,
    signal?: AbortSignal
  ): Promise<AssessmentScaleConfigDetail>;
  loginPatient(
    input: PatientLoginInput,
    signal?: AbortSignal
  ): Promise<PatientPortal>;
  verifyPatientTask(
    input: PatientTaskVerifyInput,
    signal?: AbortSignal
  ): Promise<PatientPortal>;
  verifyPatientScanToken(
    token: string,
    signal?: AbortSignal
  ): Promise<PatientPortal>;
  listPatientNotifications(
    unreadOnly?: boolean,
    signal?: AbortSignal
  ): Promise<{ items: PatientNotification[]; unreadCount: number }>;
  markPatientNotificationRead(
    notificationId: string,
    signal?: AbortSignal
  ): Promise<PatientNotification>;
  listPatientWardGuide(signal?: AbortSignal): Promise<WardGuide[]>;
  createPatientAssistantSession(
    channelType?: 'text' | 'voice',
    signal?: AbortSignal
  ): Promise<PatientAssistantSession>;
  getPatientAssistantSession(
    sessionNo: string,
    signal?: AbortSignal
  ): Promise<PatientAssistantSession>;
  sendPatientAssistantMessage(
    sessionNo: string,
    content: string,
    clientMessageId?: string,
    signal?: AbortSignal
  ): Promise<PatientAssistantSession>;
  getConsentSnapshot(
    taskId: string,
    signal?: AbortSignal
  ): Promise<ConsentSnapshot>;
  recordConsentPlayback(
    taskId: string,
    input: {
      clauseId: number;
      eventType: 'start' | 'pause' | 'resume' | 'complete' | 'replay';
      positionSeconds: number;
      clientInvocationId?: string;
    },
    signal?: AbortSignal
  ): Promise<Record<string, unknown>>;
  confirmConsentClause(
    taskId: string,
    clauseId: number,
    input: {
      confirmationResult: '已理解并确认' | '未理解' | '拒绝' | '不确定';
      patientReply?: string;
    },
    signal?: AbortSignal
  ): Promise<Record<string, unknown>>;
  loginStaff(input: StaffLoginInput, signal?: AbortSignal): Promise<User>;
  getCurrentStaff(signal?: AbortSignal): Promise<User>;
  logoutStaff(signal?: AbortSignal): Promise<void>;
  listPatientTasks(signal?: AbortSignal): Promise<CareTask[]>;
  listMyTasks(signal?: AbortSignal): Promise<CareTask[]>;
  createTask(input: CreateTaskInput, signal?: AbortSignal): Promise<CareTask>;
  getTask(taskId: string, signal?: AbortSignal): Promise<CareTask>;
  retryTaskPreparation(
    taskId: string,
    signal?: AbortSignal
  ): Promise<CareTask>;
  getNursingPlan(
    taskId: string,
    signal?: AbortSignal
  ): Promise<NursingPlan | null>;
  generateNursingPlan(
    taskId: string,
    force?: boolean,
    signal?: AbortSignal
  ): Promise<NursingPlan>;
  updateNursingPlan(
    taskId: string,
    input: NursingPlanUpdate,
    signal?: AbortSignal
  ): Promise<NursingPlan>;
  confirmNursingPlan(
    taskId: string,
    signal?: AbortSignal
  ): Promise<NursingPlan>;
  getDialogueSnapshot(
    task: CareTask,
    signal?: AbortSignal
  ): Promise<DialogueSnapshot>;
  updateManualField(
    sessionId: string,
    input: ManualFieldUpdateInput,
    signal?: AbortSignal
  ): Promise<DialogueSnapshot>;
  sendDialogMessage(
    input: SendMessageInput,
    signal?: AbortSignal
  ): Promise<void>;
  saveQuestionnaireDraft(
    taskId: string,
    answers: Record<string, PrototypeAnswerValue>,
    signal?: AbortSignal
  ): Promise<void>;
  submitQuestionnaire(
    taskId: string,
    answers: Record<string, PrototypeAnswerValue>,
    signal?: AbortSignal
  ): Promise<void>;
  getQuestionnaire(
    taskId: string,
    signal?: AbortSignal
  ): Promise<QuestionnaireSnapshot>;
  pauseDialogue(sessionId: string, signal?: AbortSignal): Promise<void>;
  resumeDialogue(sessionId: string, signal?: AbortSignal): Promise<void>;
  requestHandoff(
    taskId: string,
    reason: string,
    details?: {
      requestedAction?: string;
      urgency?: 'routine' | 'urgent';
      clientInvocationId?: string;
    },
    signal?: AbortSignal
  ): Promise<Record<string, unknown>>;
  resolveHandoff(
    taskId: string,
    requestId?: string,
    signal?: AbortSignal
  ): Promise<Record<string, unknown>>;
  submitMessageFeedback(
    feedback: MessageFeedback,
    signal?: AbortSignal
  ): Promise<void>;
  listMessageFeedback(
    taskId: string,
    reviewerId?: string,
    signal?: AbortSignal
  ): Promise<MessageFeedback[]>;
  submitConsent(
    consent: ConsentProgress,
    signal?: AbortSignal
  ): Promise<void>;
  acknowledgeEducation(
    taskId: string,
    eventId: string,
    materialId: string,
    signal?: AbortSignal
  ): Promise<Record<string, unknown>>;
  submitQualityReview(
    review: QualityReview,
    signal?: AbortSignal
  ): Promise<void>;
  getQualityReview(
    taskId: string,
    reviewerId?: string,
    signal?: AbortSignal
  ): Promise<QualityReview | null>;
  submitAssessmentReview(
    review: AssessmentReview,
    signal?: AbortSignal
  ): Promise<void>;
}
