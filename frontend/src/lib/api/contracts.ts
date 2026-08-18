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
  patient_name: string;
  sex?: string;
  birthday?: string;
  phone?: string;
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
  encounter_status: string;
  diagnosis_snapshot?: Record<string, unknown>;
}

export interface InHospitalPatientDto {
  patient: PatientDto;
  encounter: PatientEncounterDto;
}

export interface PatientLoginRequest {
  id_card_no: string;
  phone: string;
}

export interface PatientLoginResponse {
  patient: PatientDto;
  encounter: PatientEncounterDto;
  tasks: BackendTaskDto[];
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

export interface BackendTaskDto {
  id?: ApiId;
  task_id?: ApiId;
  task_no: string;
  session_id?: ApiId;
  patient_id: ApiId;
  encounter_id: ApiId;
  encounter_no?: string;
  patient_name?: string;
  bed_no?: string;
  department?: string;
  ward_name?: string;
  task_type?: string;
  collection_mode: CollectionMode;
  task_status: TaskStatus;
  nurse_id?: ApiId;
  assigned_nurse_id?: ApiId;
  assigned_nurse_name?: string;
  scale_ids?: ApiId[];
  scale_names?: string[];
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
  answer_text?: string;
  answer_number?: number;
  answer_boolean?: boolean;
  selected_options?: string[];
  source_message_ids?: string[];
  confidence?: number;
  corrected?: boolean;
}

export interface ExtractedFieldsResponse {
  session_id: ApiId;
  fields: ExtractedFieldDto[];
}

export interface RatingRequest {
  task_id: string;
  message_id: string;
  rating: 'like' | 'dislike';
  issue_tags: string[];
  comment?: string;
}

export interface QualityReviewRequest {
  task_id: string;
  dialogue_scores: Record<string, number>;
  assessment_scores: Record<string, number>;
  comment?: string;
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
}

export type SseEventType =
  | 'session_snapshot'
  | 'session_status'
  | 'user_transcript_delta'
  | 'user_transcript_completed'
  | 'assistant_message_started'
  | 'assistant_text_delta'
  | 'assistant_audio_delta'
  | 'assistant_message_completed'
  | 'extraction_updated'
  | 'progress_updated'
  | 'education_triggered'
  | 'education_status_updated'
  | 'consent_triggered'
  | 'handoff_requested'
  | 'handoff_resolved'
  | 'task_status_updated'
  | 'error'
  | 'heartbeat';

export interface SseEnvelope<TPayload = Record<string, unknown>> {
  event_id: string;
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
  | { type: 'close' };

export type VoiceServerMessage =
  | { type: 'ready' }
  | { type: 'state'; state: 'listening' | 'transcribing' | 'thinking' | 'speaking' }
  | { type: 'audio'; sequence: number; sample_rate: number; audio_base64: string }
  | { type: 'error'; code?: string; message: string }
  | { type: 'closed' };
