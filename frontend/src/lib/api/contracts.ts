import type {
  AssessmentScene,
  CollectionMode,
  ConsentClause,
  ParticipantType,
  TaskStatus,
} from '@/lib/types';

export type ApiId = string | number;

export interface ApiResponse<T> {
  code: string;
  message: string;
  data: T;
}

export interface PatientDto {
  id: ApiId;
  patient_no: string;
  his_patient_id?: string;
  patient_name: string;
  sex?: string;
  birthday?: string;
  phone?: string;
  id_card_masked?: string;
  emergency_contact_name?: string;
  emergency_contact_relation?: string;
  emergency_contact_phone?: string;
  address?: string;
}

export interface PatientEncounterDto {
  id: ApiId;
  encounter_no: string;
  inpatient_no?: string;
  patient_id: ApiId;
  department_code?: string;
  department_name?: string;
  ward_name?: string;
  bed_no?: string;
  admission_time: string;
  discharge_time?: string;
  encounter_status: string;
  diagnosis_snapshot?: Record<string, unknown>;
  admission_source?: string;
  nursing_level?: string;
  insurance_type?: string;
  allergy_summary?: string;
}

export interface PatientTaskSummaryDto {
  total: number;
  pending_review: number;
  in_progress: number;
  handoff_required: boolean;
}

export interface PatientRecordDto {
  patient: PatientDto;
  encounter: PatientEncounterDto;
  task_summary?: PatientTaskSummaryDto;
}

export type InHospitalPatientDto = PatientRecordDto;

export interface PatientLoginRequest {
  id_card_no: string;
  phone: string;
}

export interface PatientLoginResponse {
  patient: PatientDto;
  encounter: PatientEncounterDto;
  tasks: BackendTaskDto[];
}

export interface PatientNotificationDto {
  id: ApiId;
  notification_no: string;
  notification_type: string;
  title: string;
  content: string;
  priority: string;
  payload: Record<string, unknown>;
  read_at?: string | null;
  created_at: string;
}

export interface WardGuideDto {
  id: ApiId;
  guide_code: string;
  category: string;
  title: string;
  content: string;
  department_name?: string | null;
  ward_name?: string | null;
  sort_no: number;
}

export interface PatientAssistantMessageDto {
  message_no: string;
  role: 'patient' | 'assistant' | 'system';
  content: string;
  result_status?: string | null;
  source_guide_id?: ApiId | null;
  occurred_at: string;
}

export interface PatientAssistantSessionDto {
  session_no: string;
  channel_type: string;
  session_status: string;
  handoff_required: boolean;
  handoff_reason?: string | null;
  messages: PatientAssistantMessageDto[];
}

export interface ConsentSnapshotDto {
  task_no: string;
  record_id: number;
  consent_code: string;
  consent_name: string;
  consent_type: string;
  document_version: string;
  full_text: string;
  record_status: string;
  patient_confirmed: boolean;
  participant_type: string;
  clauses: Array<Record<string, unknown>>;
  confirmations: Array<Record<string, unknown>>;
  playback: Array<Record<string, unknown>>;
  participants: Array<Record<string, unknown>>;
  signatures: Array<Record<string, unknown>>;
}

export interface StaffDto {
  id: ApiId;
  staff_no: string;
  staff_name: string;
  role_code: string;
  department_name?: string;
}

export interface StaffLoginResponse {
  staff: StaffDto;
}

export interface AssessmentScaleDto {
  id: ApiId;
  scale_code: string;
  scale_name: string;
  scale_type: string;
  question_count: number;
  version_code: string;
  description?: string;
}

export interface EducationMaterialConfigDto {
  id: ApiId;
  version_id: ApiId;
  unit_id: ApiId;
  category: string;
  title: string;
  document_version: string;
  original_content: string;
  patient_content: string;
  spoken_content: string;
  source_name?: string | null;
  priority: 'low' | 'medium' | 'high';
  requires_acknowledgement: boolean;
  auto_play: boolean;
  enabled: boolean;
}

export interface InteractionRuleConfigDto {
  id: ApiId;
  rule_code: string;
  rule_name: string;
  scope_type: string;
  scope_id?: ApiId | null;
  keywords: string[];
  patterns: string[];
  action_type: string;
  prompt: string;
  tags: string[];
  priority: number;
  enabled: boolean;
}

export interface InteractionRuleMatchDto {
  rule_code: string;
  rule_name: string;
  matched_terms: string[];
  action_type: string;
  prompt: string;
  priority: number;
}

export interface AssessmentScaleConfigSummaryDto {
  id: ApiId;
  scale_code: string;
  scale_name: string;
  scale_type: string;
  clinical_purpose?: string | null;
  status: string;
  version_id: ApiId;
  version_code: string;
  version_name: string;
  publish_status: string;
  section_count: number;
  question_count: number;
  option_count: number;
  rule_count: number;
  action_count: number;
}

export interface TaskScaleProgressDto {
  scale_id: ApiId;
  scale_name: string;
  answered_question_count: number;
  total_question_count: number;
  status: 'pending' | 'collecting' | 'completed';
}

export interface TaskPreparationStageDto {
  status: 'pending' | 'running' | 'completed' | 'failed';
  output?: Record<string, unknown>;
  error?: string | null;
  updated_at?: string | null;
}

export interface TaskPreparationDto {
  status: 'not_required' | 'queued' | 'running' | 'ready' | 'failed';
  stage?: string | null;
  attempt: number;
  error?: string | null;
  patient_visible_at?: string | null;
  stages: Record<string, TaskPreparationStageDto>;
}

export interface BackendTaskDto {
  id?: ApiId;
  task_id?: ApiId;
  task_no: string;
  session_id?: ApiId;
  patient_id: ApiId;
  encounter_id: ApiId;
  encounter_no?: string;
  patient_name?: string;
  inpatient_no?: string;
  bed_no?: string;
  department?: string;
  ward_name?: string;
  sex?: string;
  age?: number;
  admission_time?: string;
  encounter_status?: string;
  task_type?: string;
  collection_mode: CollectionMode;
  task_status: TaskStatus;
  preparation?: TaskPreparationDto | null;
  nurse_id?: ApiId;
  assigned_nurse_id?: ApiId;
  assigned_nurse_name?: string;
  scale_ids?: ApiId[];
  scale_names?: string[];
  scale_progress?: TaskScaleProgressDto[];
  scale_version?: string;
  participant_type?: ParticipantType;
  participant_name?: string;
  relationship_to_patient?: string;
  assessment_scene?: AssessmentScene;
  consent_required?: boolean;
  education_topics?: string[];
  planned_start_time?: string;
  notes?: string;
  handoff_required?: boolean;
  handoff_reason?: string;
  current_stage?: string;
  ai_summary?: string;
  answered_question_count?: number;
  total_question_count?: number;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  need_manual_intervention?: boolean;
  intervention_reason?: string;
}

export interface PatientProfileDto {
  id: ApiId;
  profile_no: string;
  source_submission_ids: ApiId[];
  cooperation_level: string;
  cognition_level: string;
  self_care_level: string;
  fall_risk_level: string;
  pressure_risk_level: string;
  nutrition_risk_level: string;
  communication_level: string;
  education_need_level: string;
  profile_detail: Record<string, unknown>;
  generated_by: string;
  generated_at: string;
}

export interface NursingPlanItemDto {
  id: ApiId;
  item_type: string;
  item_code: string;
  item_content: string;
  source_type: string;
  source_id?: string | null;
  priority: 'low' | 'medium' | 'high' | string;
  nurse_action: 'pending' | 'accepted' | 'modified' | 'rejected' | string;
  nurse_comment?: string | null;
}

export interface NursingPlanDto {
  id: ApiId;
  task_id: ApiId;
  plan_no: string;
  plan_status: string;
  risk_summary: string;
  education_summary: string;
  handover_summary: string;
  generated_by: string;
  confirmed_by?: ApiId | null;
  confirmed_at?: string | null;
  profile: PatientProfileDto;
  items: NursingPlanItemDto[];
}

export interface CreateTaskRequest {
  patient_id: number;
  encounter_id: number;
  assigned_nurse_id?: number;
  scale_ids: number[];
  collection_mode: CollectionMode;
  participant_type: ParticipantType;
  assessment_scene: AssessmentScene;
  planned_start_time?: string;
  task_type?: string;
  task_name?: string;
  task_source?: string;
}

export interface CreateTaskResponse {
  task_id: ApiId;
  task_no: string;
  session_id?: ApiId;
  status?: TaskStatus;
  task?: BackendTaskDto;
}

export interface QuestionnaireOptionDto {
  id: ApiId;
  option_code: string;
  option_label: string;
  option_value: string;
  clinical_score?: number | null;
  requires_follow_up?: boolean;
  extra_input_type?: string | null;
  extra_input_unit?: string | null;
}

export interface QuestionnaireQuestionDto {
  id: ApiId;
  scale_id: ApiId;
  scale_name: string;
  scale_version_id: ApiId;
  section_id?: ApiId | null;
  section_name?: string | null;
  question_code: string;
  question_text: string;
  question_type: string;
  value_type: string;
  required: boolean;
  scored: boolean;
  derived: boolean;
  unit?: string | null;
  value_precision?: number | null;
  allow_other?: boolean;
  validation_rule?: Record<string, unknown> | null;
  sort_no: number;
  options?: QuestionnaireOptionDto[];
}

export interface QuestionnaireAnswerDto {
  question_id: ApiId;
  question_code: string;
  answer_type: string;
  answer_text?: string | null;
  answer_number?: number | null;
  answer_boolean?: boolean | null;
  answer_date?: string | null;
  selected_options?: string[];
  selected_option_labels?: string[];
  selected_option_values?: string[];
  display_value?: string | null;
  clinical_score?: number | null;
}

export interface QuestionnaireScoreDto {
  scale_id: ApiId;
  scale_name: string;
  total_score?: number | null;
  risk_level?: string | null;
  result_summary?: string | null;
}

export interface QuestionnaireDto {
  task_id: ApiId;
  task_no: string;
  collection_mode: 'traditional_form';
  status:
    | 'not_started'
    | 'in_progress'
    | 'submitted'
    | 'returned'
    | 'confirmed';
  questions: QuestionnaireQuestionDto[];
  answers: QuestionnaireAnswerDto[];
  scores: QuestionnaireScoreDto[];
  submitted_at?: string | null;
  updated_at?: string | null;
}

export interface SendDialogMessageRequest {
  session_id: string;
  task_id: string;
  content: string;
  client_message_id: string;
  input_mode: 'text' | 'voice';
}

export interface DialogMessageDto {
  message_id?: string;
  message_no?: string;
  session_id?: ApiId;
  turn_no: number;
  role?: 'assistant' | 'ai' | 'patient' | 'user' | 'system';
  role_type?: string;
  message_type?: string;
  cicare_stage?: string;
  intent_type?: string;
  content_text?: string;
  audio_url?: string;
  asr_text?: string;
  tts_text?: string;
  occurred_at?: string;
  related_question_ids?: ApiId[];
}

export interface DialogHistoryResponse {
  session_id?: ApiId;
  session_no?: ApiId;
  task_id?: ApiId;
  task_no?: string;
  session_status?: string;
  current_cicare_stage?: string;
  answered_question_count?: number;
  total_question_count?: number;
  ai_summary?: string;
  messages: DialogMessageDto[];
}

export interface ExtractedFieldDto {
  field_id?: ApiId;
  question_id: ApiId;
  question_code: string;
  question_text: string;
  answer_type?: string;
  options?: Array<{ code: string; label: string; value?: string; score?: number | null }>;
  answer_text?: string;
  answer_number?: number;
  answer_boolean?: boolean;
  selected_options?: string[];
  selected_option_labels?: string[];
  selected_option_values?: string[];
  display_value?: string;
  source_message_ids?: string[];
  confidence?: number;
  corrected?: boolean;
  invalid?: boolean;
  invalid_reason?: string;
  raw_answer?: Record<string, unknown>;
}

export interface ExtractedFieldsResponse {
  session_id: ApiId;
  fields: ExtractedFieldDto[];
  task_id?: ApiId;
  manual_intervention?: boolean;
  intervention_reason?: string;
}

export interface RatingRequest {
  task_id: string;
  message_id: string;
  reviewer_id: number;
  rating?: 'like' | 'dislike';
  score?: number;
  issue_tags: string[];
  comment?: string;
}

export interface MessageRatingDto {
  feedback_id: ApiId;
  task_id: ApiId;
  message_id: ApiId;
  reviewer_id: ApiId;
  rating: 'like' | 'dislike';
  score?: number;
  issue_tags: string[];
  comment?: string;
  reviewed_at: string;
}

export interface MessageRatingListResponse {
  items: MessageRatingDto[];
}

export interface QualityReviewRequest {
  task_id: string;
  reviewer_id: number;
  dialogue_scores: Record<string, number>;
  assessment_scores: Record<string, number>;
  dialogue_comments?: Record<string, string>;
  assessment_comments?: Record<string, string>;
  evidence_message_ids?: Record<string, string[]>;
  evidence_question_ids?: Record<string, string[]>;
  comment?: string;
}

export interface QualityReviewDto {
  task_id: ApiId;
  reviewer_id: ApiId;
  dialogue_scores: Record<string, number>;
  assessment_scores: Record<string, number>;
  dialogue_comments?: Record<string, string>;
  assessment_comments?: Record<string, string>;
  comment?: string;
  submitted_at?: string;
}

export interface ConsentSignRequest {
  task_id: string;
  participant_name: string;
  decision: 'agreed' | 'refused' | 'needs_explanation';
  signature_data?: string;
  clauses: ConsentClause[];
}

export interface HandoffRequest {
  task_id: string;
  reason: string;
  client_invocation_id?: string;
}

export type SseEventType =
  | 'session_snapshot'
  | 'session_status'
  | 'user_transcript_delta'
  | 'user_transcript_completed'
  | 'patient_audio_delta'
  | 'assistant_message_started'
  | 'assistant_text_delta'
  | 'assistant_audio_delta'
  | 'assistant_message_completed'
  | 'extraction_updated'
  | 'progress_updated'
  | 'education_triggered'
  | 'education_status_updated'
  | 'consent_triggered'
  | 'consent_status_updated'
  | 'handoff_requested'
  | 'handoff_resolved'
  | 'task_status_updated'
  | 'error'
  | 'heartbeat';

export interface SseEnvelope<TPayload = Record<string, unknown>> {
  event_id: string;
  stream_id?: string;
  event_type: SseEventType;
  task_id: string;
  session_id?: string;
  message_id?: string;
  occurred_at: string;
  payload: TPayload;
}

export type VoiceClientMessage =
  | {
      type: 'start';
      task_id: string;
      session_id: string;
      format: 'pcm_s16le';
      sample_rate: 16000;
      channels: 1;
    }
  | { type: 'commit' }
  | { type: 'interrupt' }
  | { type: 'pause' }
  | { type: 'resume' }
  | { type: 'confirm_transcript'; transcript_id: string }
  | { type: 'retry_transcript'; transcript_id: string }
  | { type: 'close' };

export type VoiceServerMessage =
  | { type: 'ready' }
  | { type: 'mode'; turn_detection: 'server_vad' | 'smart_turn' | 'manual' }
  | { type: 'speech_started' }
  | { type: 'speech_stopped' }
  | { type: 'interrupted' }
  | { type: 'response_completed'; response_id?: string }
  | {
      type: 'state';
      state:
        | 'listening'
        | 'transcribing'
        | 'thinking'
        | 'speaking'
        | 'paused';
    }
  | { type: 'audio'; sequence: number; sample_rate: number; audio_base64: string }
  | {
      type: 'transcript_ready';
      transcript_id: string;
      text: string;
      turn_no: number;
      message_id?: string;
      audio_url?: string | null;
      is_final: boolean;
    }
  | { type: 'transcript_confirmed'; transcript_id: string }
  | { type: 'transcript_discarded'; transcript_id: string }
  | { type: 'error'; code?: string; message: string }
  | { type: 'closed' };
