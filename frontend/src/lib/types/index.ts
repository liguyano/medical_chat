// ============================================================
// 基础类型定义（基于 DDL 结构）
// ============================================================

export * from './systemConfig';
export * from './nursingPlan';

// 用户角色
export type UserRole = 'nurse' | 'patient';

// 用户信息
export interface User {
  id: string;
  role: UserRole;
  name: string;
  department?: string;
  avatar?: string;
  username?: string;
}

// 患者信息
export interface Patient {
  id: string;
  patientNo: string;
  hisPatientId?: string;
  name: string;
  gender: 'male' | 'female' | 'other';
  age: number;
  birthday?: string;
  idCard?: string; // 脱敏值
  phone?: string;
  emergencyContactName?: string;
  emergencyContactRelation?: string;
  emergencyContactPhone?: string;
  address?: string;
}

// 住院记录
export interface PatientEncounter {
  id: string;
  patientId: string;
  encounterNo: string;
  inpatientNo: string;
  departmentCode?: string;
  department: string;
  ward: string;
  bedNo: string;
  admissionDate: string;
  dischargeDate?: string;
  diagnosis: string;
  diagnosisSnapshot?: Record<string, unknown>;
  encounterStatus:
    | 'pending_admission'
    | 'in_hospital'
    | 'discharged'
    | 'cancelled';
  admissionSource?: string;
  nursingLevel?: string;
  insuranceType?: string;
  allergySummary?: string;
}

// 任务状态
export type TaskStatus =
  | 'pending'
  | 'in_progress'
  | 'pending_review'
  | 'completed'
  | 'cancelled';

// 采集模式
export type CollectionMode = 'traditional_form' | 'ai_dialogue';
export type ParticipantType = 'patient' | 'family' | 'agent';
export type AssessmentScene = 'admission' | 'reassessment' | 'transfer' | 'discharge';
export type PrototypeAnswerValue = string | string[] | number | boolean | null;

export interface TaskScaleProgress {
  scaleId: string;
  scaleName: string;
  answeredQuestionCount: number;
  totalQuestionCount: number;
  status: 'pending' | 'collecting' | 'completed';
}

export type TaskPreparationStatus =
  | 'not_required'
  | 'queued'
  | 'running'
  | 'ready'
  | 'failed';

export type TaskPreparationStageStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed';

export interface TaskPreparationStage {
  status: TaskPreparationStageStatus;
  output: Record<string, unknown>;
  error?: string | null;
  updatedAt?: string | null;
}

export interface TaskPreparation {
  status: TaskPreparationStatus;
  stage?: string | null;
  attempt: number;
  error?: string | null;
  patientVisibleAt?: string | null;
  stages: Record<string, TaskPreparationStage>;
}

// 护理任务
export interface CareTask {
  id: string;
  taskNo: string;
  sessionId?: string;
  patientId: string;
  encounterId: string;
  encounterNo?: string;
  inpatientNo?: string;
  parentTaskId?: string;
  patientName: string;
  bedNo: string;
  department?: string;
  wardName?: string;
  sex?: string;
  age?: number;
  admissionDate?: string;
  encounterStatus?: string;
  taskType: string;
  collectionMode: CollectionMode;
  taskStatus: TaskStatus;
  assignedNurseId: string;
  assignedNurseName: string;
  scaleId?: string;
  scaleName?: string;
  scaleVersion?: string;
  scaleIds?: string[];
  scaleNames?: string[];
  scaleProgress?: TaskScaleProgress[];
  participantType?: ParticipantType;
  participantName?: string;
  relationshipToPatient?: string;
  assessmentScene?: AssessmentScene;
  consentRequired?: boolean;
  educationTopics?: string[];
  plannedStartTime?: string;
  notes?: string;
  preparation?: TaskPreparation;
  handoffRequired?: boolean;
  handoffReason?: string;
  handoffRequestId?: string;
  handoffRequestedAction?: string;
  handoffActionLabel?: string;
  handoffUrgency?: 'routine' | 'urgent';
  currentStage?: CicareStage;
  aiSummary?: string;
  createdAt: string;
  updatedAt?: string;
  completedAt?: string;
  needManualIntervention?: boolean;
  interventionReason?: string;
  progress?: {
    current: number;
    total: number;
  };
}

// 量表配置
export interface AssessmentScale {
  id: string;
  scaleCode: string;
  scaleName: string;
  scaleType: string;
  description: string;
}

// 量表版本
export interface AssessmentScaleVersion {
  id: string;
  scaleId: string;
  versionCode: string;
  sections: AssessmentSection[];
}

// 量表分组
export interface AssessmentSection {
  id: string;
  sectionCode: string;
  sectionTitle: string;
  sequenceNo: number;
  questions: AssessmentQuestion[];
}

// 题目类型
export type QuestionType =
  | 'single_choice'
  | 'multiple_choice'
  | 'text'
  | 'number'
  | 'date'
  | 'boolean'
  | 'derived';

export type ConditionalOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'greater_than'
  | 'less_than';

export interface QuestionDisplayCondition {
  questionId: string;
  operator: ConditionalOperator;
  value: string | number | boolean;
}

export interface QuestionValidationRule {
  min?: number;
  max?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
}

// 量表题目
export interface AssessmentQuestion {
  id: string;
  questionCode: string;
  sectionId?: string;
  sectionName?: string;
  questionText: string;
  description?: string;
  questionType: QuestionType;
  required: boolean;
  scored: boolean;
  derived: boolean;
  displayOrder?: number;
  placeholder?: string;
  unit?: string;
  options?: AssessmentOption[];
  validationRule?: QuestionValidationRule;
  conditionalLogic?: {
    showIf: QuestionDisplayCondition[];
  };
  calculationExpression?: string;
}

// 题目选项
export interface AssessmentOption {
  id?: string;
  optionCode: string;
  optionLabel: string;
  description?: string;
  displayOrder?: number;
  clinicalScore?: number;
  requiresFollowUp?: boolean;
}

export interface QuestionnaireAnswer {
  questionId: string;
  questionCode: string;
  answerType: string;
  answerText?: string;
  answerNumber?: number;
  answerBoolean?: boolean;
  answerDate?: string;
  selectedOptions: string[];
  selectedOptionLabels: string[];
  selectedOptionValues: string[];
  displayValue?: string;
  clinicalScore?: number;
}

export interface QuestionnaireScore {
  scaleId: string;
  scaleName: string;
  totalScore?: number;
  riskLevel?: string;
  resultSummary?: string;
}

export type QuestionnaireStatus =
  | 'not_started'
  | 'in_progress'
  | 'submitted'
  | 'returned'
  | 'confirmed';

export interface QuestionnaireSnapshot {
  taskId: string;
  taskNo: string;
  status: QuestionnaireStatus;
  questions: AssessmentQuestion[];
  answers: QuestionnaireAnswer[];
  answerValues: Record<string, PrototypeAnswerValue>;
  scores: QuestionnaireScore[];
  submittedAt?: string;
  updatedAt?: string;
}

// CICARE 阶段
export type CicareStage =
  | 'connect'
  | 'introduce'
  | 'communicate'
  | 'ask'
  | 'respond'
  | 'exit';

// 对话角色
export type MessageRole = 'ai' | 'patient' | 'system';

// 对话消息
export interface InteractionMessage {
  id: string;
  sessionId: string;
  messageNo: string;
  turnNo: number;
  role: MessageRole;
  cicareStage?: CicareStage;
  intentType?: 'greeting' | 'question' | 'answer' | 'follow_up' | 'education' | 'confirmation';
  contentText: string;
  audioUrl?: string;
  occurredAt: string;
  relatedQuestionIds?: string[];
  structuredAnswer?: Record<string, string | number | boolean>;
  isStreaming?: boolean; // 前端状态：是否正在流式输出
}

// 对话会话
export interface InteractionSession {
  id: string;
  sessionNo: string;
  taskId: string;
  patientId: string;
  encounterId: string;
  interactionType: string;
  channelType: 'text' | 'voice' | 'mixed';
  sessionStatus: 'pending' | 'active' | 'paused' | 'completed' | 'interrupted';
  startedAt?: string;
  completedAt?: string;
  currentCicareStage: CicareStage;
  answeredQuestionCount?: number;
  totalQuestionCount?: number;
  handoffRequired?: boolean;
  handoffReason?: string;
  aiSummary?: string;
  messages: InteractionMessage[];
}

// 结构化答案
export interface StructuredAnswer {
  questionId: string;
  questionCode: string;
  questionText: string;
  answerText?: string;
  answerNumber?: number;
  answerBoolean?: boolean;
  selectedOptions?: string[]; // option codes, retained for audit
  selectedOptionLabels?: string[]; // user-visible scale labels
  selectedOptionValues?: string[]; // scale value snapshots
  displayValue?: string; // normalized user-visible answer
  sourceMessageIds: string[];
  extractionConfidence: number;
  corrected: boolean; // 患者是否已纠正
  answerType?: 'text' | 'number' | 'boolean' | 'date' | 'single_choice' | 'multiple_choice';
  options?: Array<{ code: string; label: string; value?: string; score?: number | null }>;
  invalid?: boolean;
  invalidReason?: string;
  rawAnswer?: Record<string, unknown>;
}

// 评估提交
export interface AssessmentSubmission {
  id: string;
  instanceId: string;
  submissionType: 'ai_extracted' | 'nurse_independent' | 'final_confirmed';
  submittedBy: string;
  submittedAt: string;
  totalQuestionCount: number;
  answeredQuestionCount: number;
  confidenceScore?: number;
  answers: StructuredAnswer[];
  scores?: AssessmentScore[];
}

// 评估分数
export interface AssessmentScore {
  scoreCode: string;
  scoreName: string;
  scoreValue: number;
  riskLevel: 'low' | 'medium' | 'high' | 'very_high';
}

// 宣教内容卡片
export interface EducationCard {
  id: string;
  taskId: string;
  materialId: string;
  category: string;
  title: string;
  documentVersion: string;
  originalContent: string;
  patientContent: string;
  spokenContent: string;
  sourceName?: string;
  priority: 'low' | 'medium' | 'high';
  requiresAcknowledgement: boolean;
  autoPlay: boolean;
  acknowledged: boolean;
  acknowledgedAt?: string;
  occurredAt: string;
  messageId?: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  toolResult?: Record<string, unknown>;
}

// 知情同意条款
export interface ConsentClause {
  id: string;
  clauseCode: string;
  clauseName: string;
  patientContent: string;
  importanceLevel: 'normal' | 'important' | 'critical';
  mandatoryDelivery: boolean;
  explicitConfirmationRequired: boolean;
  deliveryStatus: 'pending' | 'delivering' | 'delivered' | 'skipped';
  listened: boolean;
  confirmed: boolean;
  understandingStatus?: 'pending' | 'understood' | 'not_understood' | 'refused';
}

export interface InteractionEvent {
  id: string;
  taskId: string;
  messageId?: string;
  eventType: 'risk' | 'follow_up' | 'education' | 'handoff' | 'refusal';
  title: string;
  description: string;
  priority: 'low' | 'medium' | 'high';
  handled: boolean;
  occurredAt: string;
  metadata?: Record<string, unknown>;
}

export interface ConsentRequest {
  id: string;
  taskId: string;
  formId: string;
  formType: string;
  title: string;
  documentVersion: string;
  fullText: string;
  clauses: ConsentClause[];
  status:
    | 'pending_signature'
    | 'signed'
    | 'refused'
    | 'needs_explanation';
  requiresSignature: boolean;
  autoPlay: boolean;
  occurredAt: string;
  messageId?: string;
  decision?: ConsentProgress['decision'];
  completedAt?: string;
  signatureFileUrl?: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  toolResult?: Record<string, unknown>;
}

export interface NurseAssistanceRequest {
  requestId: string;
  taskId: string;
  patientName?: string;
  bedNo?: string;
  wardName?: string;
  reason: string;
  requestedAction: string;
  actionLabel: string;
  urgency: 'routine' | 'urgent';
  status: 'requested' | 'resolved';
  occurredAt: string;
  requestSource: 'patient' | 'agent';
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  toolResult?: Record<string, unknown>;
  handledAt?: string;
  resolvedByStaffId?: string;
  resolvedByStaffNo?: string;
  resolvedByName?: string;
  resolution?: string;
}

export interface MessageFeedback {
  messageId: string;
  taskId: string;
  reviewerId?: string;
  feedbackType: 'like' | 'dislike';
  score?: number;
  issueTags: string[];
  comment?: string;
  reviewedAt: string;
}

export interface AssessmentReview {
  taskId: string;
  nurseAnswers: Record<string, string>;
  finalAnswers: Record<string, string>;
  correctionReasons: Record<string, string>;
  supplementaryInquiry?: string;
  status: 'draft' | 'returned' | 'confirmed';
  reviewedAt?: string;
}

export interface QualityReview {
  taskId: string;
  reviewerId?: string;
  dialogueScores: Record<string, number>;
  assessmentScores: Record<string, number>;
  dialogueComments?: Record<string, string>;
  assessmentComments?: Record<string, string>;
  evidenceMessageIds?: Record<string, string[]>;
  evidenceQuestionIds?: Record<string, string[]>;
  comment?: string;
  submittedAt?: string;
}

export interface ConsentProgress {
  taskId: string;
  formId?: string;
  documentVersion?: string;
  clauses: ConsentClause[];
  participantName: string;
  decision: 'pending' | 'agreed' | 'refused' | 'needs_explanation';
  signatureData?: string;
  completedAt?: string;
}
