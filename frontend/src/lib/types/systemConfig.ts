export interface EducationMaterialConfig {
  id: string;
  versionId: string;
  unitId: string;
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
  enabled: boolean;
}

export type EducationMaterialUpdate = Omit<
  EducationMaterialConfig,
  'id' | 'versionId' | 'unitId' | 'category'
>;

export interface InteractionRuleConfig {
  id: string;
  ruleCode: string;
  ruleName: string;
  scopeType: string;
  scopeId?: string;
  keywords: string[];
  patterns: string[];
  actionType: string;
  prompt: string;
  tags: string[];
  priority: number;
  enabled: boolean;
}

export type InteractionRuleUpdate = Omit<
  InteractionRuleConfig,
  'id' | 'ruleCode'
>;

export interface InteractionRuleMatch {
  ruleCode: string;
  ruleName: string;
  matchedTerms: string[];
  actionType: string;
  prompt: string;
  priority: number;
}

export interface AssessmentScaleConfigSummary {
  id: string;
  scaleCode: string;
  scaleName: string;
  scaleType: string;
  clinicalPurpose?: string;
  status: string;
  versionId: string;
  versionCode: string;
  versionName: string;
  publishStatus: string;
  sectionCount: number;
  questionCount: number;
  optionCount: number;
  ruleCount: number;
  actionCount: number;
}

export interface AssessmentSectionConfig {
  id: number;
  parent_section_id?: number | null;
  section_code: string;
  section_name: string;
  section_description?: string | null;
  display_condition?: Record<string, unknown> | null;
  sort_no: number;
}

export interface AssessmentQuestionConfig {
  id: number;
  section_id?: number | null;
  question_code: string;
  question_name: string;
  original_text: string;
  patient_text: string;
  nurse_text?: string | null;
  question_type: string;
  value_type: string;
  required: boolean;
  scored: boolean;
  unit?: string | null;
  value_precision?: number | null;
  allow_other: boolean;
  derived: boolean;
  calculation_expression?: string | null;
  validation_rule?: Record<string, unknown> | null;
  sort_no: number;
}

export interface AssessmentOptionConfig {
  id: number;
  question_id: number;
  option_code: string;
  option_label: string;
  option_value: string;
  clinical_score?: number | null;
  risk_tag?: string | null;
  requires_follow_up: boolean;
  extra_input_type?: string | null;
  extra_input_unit?: string | null;
  sort_no: number;
}

export interface AssessmentRuleConfig {
  id: number;
  rule_code: string;
  rule_type: string;
  condition_expression: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  priority: number;
  status: string;
}

export interface AssessmentActionConfig {
  id: number;
  action_code: string;
  action_group?: string | null;
  action_name: string;
  action_type: string;
  input_type: string;
  allow_other: boolean;
  trigger_rule_id?: number | null;
  sort_no: number;
}

export interface AssessmentScaleConfigDetail {
  id: number;
  scale_code: string;
  scale_name: string;
  scale_type: string;
  clinical_purpose?: string | null;
  applicable_scope?: Record<string, unknown> | null;
  source_file?: string | null;
  status: string;
  version_id: number;
  version_code: string;
  version_name: string;
  publish_status: string;
  scale_snapshot: Record<string, unknown>;
  sections: AssessmentSectionConfig[];
  questions: AssessmentQuestionConfig[];
  options: AssessmentOptionConfig[];
  rules: AssessmentRuleConfig[];
  actions: AssessmentActionConfig[];
}
