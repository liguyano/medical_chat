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
  User,
} from '@/lib/types';

export interface PatientWithEncounter {
  patient: Patient;
  encounter: PatientEncounter;
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
  listInHospitalPatients(signal?: AbortSignal): Promise<PatientWithEncounter[]>;
  listScales(signal?: AbortSignal): Promise<AssessmentScale[]>;
  loginPatient(
    input: PatientLoginInput,
    signal?: AbortSignal
  ): Promise<PatientPortal>;
  loginStaff(input: StaffLoginInput, signal?: AbortSignal): Promise<User>;
  getCurrentStaff(signal?: AbortSignal): Promise<User>;
  logoutStaff(signal?: AbortSignal): Promise<void>;
  listMyTasks(signal?: AbortSignal): Promise<CareTask[]>;
  createTask(input: CreateTaskInput, signal?: AbortSignal): Promise<CareTask>;
  getTask(taskId: string, signal?: AbortSignal): Promise<CareTask>;
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
    },
    signal?: AbortSignal
  ): Promise<void>;
  resolveHandoff(taskId: string, signal?: AbortSignal): Promise<void>;
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
