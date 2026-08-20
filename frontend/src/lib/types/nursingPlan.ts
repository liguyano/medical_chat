export type NursingPlanStatus =
  | 'ai_draft'
  | 'adjusted'
  | 'confirmed'
  | 'ended';

export type NursingPlanAction = 'pending' | 'accepted' | 'modified' | 'rejected';

export type NursingPlanPriority = 'low' | 'medium' | 'high';

export type NursingPlanItemType =
  | 'nursing_measure'
  | 'education'
  | 'observation'
  | 'handover';

export interface PatientProfile {
  id: number;
  profileNo: string;
  sourceSubmissionIds: number[];
  cooperationLevel: string;
  cognitionLevel: string;
  selfCareLevel: string;
  fallRiskLevel: string;
  pressureRiskLevel: string;
  nutritionRiskLevel: string;
  communicationLevel: string;
  educationNeedLevel: string;
  detail: Record<string, unknown>;
  generatedBy: string;
  generatedAt: string;
}

export interface NursingPlanItem {
  id: number;
  itemType: NursingPlanItemType | string;
  itemCode: string;
  itemContent: string;
  sourceType: string;
  sourceId?: string | null;
  priority: NursingPlanPriority;
  nurseAction: NursingPlanAction;
  nurseComment?: string | null;
}

export interface NursingPlan {
  id: number;
  taskId: number;
  planNo: string;
  planStatus: NursingPlanStatus | string;
  riskSummary: string;
  educationSummary: string;
  handoverSummary: string;
  generatedBy: string;
  confirmedBy?: number | null;
  confirmedAt?: string | null;
  profile: PatientProfile;
  items: NursingPlanItem[];
}

export interface NursingPlanUpdate {
  riskSummary: string;
  educationSummary: string;
  handoverSummary: string;
  items: Array<{
    id: number;
    itemContent: string;
    priority: NursingPlanPriority;
    nurseAction: NursingPlanAction;
    nurseComment?: string | null;
  }>;
}
