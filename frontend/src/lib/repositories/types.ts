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
  loginStaff(input: StaffLoginInput, signal?: AbortSignal): Promise<User>;
  getCurrentStaff(signal?: AbortSignal): Promise<User>;
  logoutStaff(signal?: AbortSignal): Promise<void>;
  listPatientTasks(signal?: AbortSignal): Promise<CareTask[]>;
  listMyTasks(signal?: AbortSignal): Promise<CareTask[]>;
  createTask(input: CreateTaskInput, signal?: AbortSignal): Promise<CareTask>;
  getTask(taskId: string, signal?: AbortSignal): Promise<CareTask>;
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
