// ============================================================
// 基础类型定义（基于 DDL 结构）
// ============================================================

// 用户角色
export type UserRole = 'nurse' | 'patient';

// 用户信息
export interface User {
  id: string;
  role: UserRole;
  name: string;
  department?: string;
  avatar?: string;
}

// 患者信息
export interface Patient {
  id: string;
  patientNo: string;
  name: string;
  gender: 'male' | 'female' | 'other';
  age: number;
  idCard?: string; // 仅后四位
  phone?: string;
}

// 住院记录
export interface PatientEncounter {
  id: string;
  patientId: string;
  encounterNo: string;
  inpatientNo: string;
  department: string;
  ward: string;
  bedNo: string;
  admissionDate: string;
  diagnosis: string;
  encounterStatus: 'in_hospital' | 'discharged' | 'transferred';
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

// 护理任务
export interface CareTask {
  id: string;
  taskNo: string;
  patientId: string;
  encounterId: string;
  patientName: string;
  bedNo: string;
  taskType: string;
  collectionMode: CollectionMode;
  taskStatus: TaskStatus;
  assignedNurseId: string;
  assignedNurseName: string;
  createdAt: string;
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
  | 'derived';

// 量表题目
export interface AssessmentQuestion {
  id: string;
  questionCode: string;
  questionText: string;
  questionType: QuestionType;
  required: boolean;
  scored: boolean;
  derived: boolean;
  options?: AssessmentOption[];
  validationRule?: Record<string, any>;
  calculationExpression?: string;
}

// 题目选项
export interface AssessmentOption {
  id: string;
  optionCode: string;
  optionLabel: string;
  clinicalScore: number;
  requiresFollowUp: boolean;
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
  cicareStage: CicareStage;
  contentText: string;
  audioUrl?: string;
  occurredAt: string;
  relatedQuestionIds?: string[];
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
  selectedOptions?: string[]; // option codes
  sourceMessageIds: string[];
  extractionConfidence: number;
  corrected: boolean; // 患者是否已纠正
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
  title: string;
  content: string;
  triggerReason: string;
  sourceQuestionId?: string;
  acknowledged: boolean;
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
}
