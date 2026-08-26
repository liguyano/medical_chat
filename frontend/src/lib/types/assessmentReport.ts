export interface AssessmentReportContent {
  overallSummary: string;
  keyFindings: string[];
  riskOverview: string[];
  nursingFocus: string[];
  followUpSuggestions: string[];
}

export interface AssessmentReportVersion {
  id: number;
  versionNo: number;
  reportStatus: string;
  generatedBy: string;
  generatedAt: string;
  confirmedBy?: number | null;
  confirmedAt?: string | null;
}

export interface AssessmentReport extends AssessmentReportVersion {
  reportNo: string;
  taskId: number;
  sourceSubmissionIds: number[];
  sourceSnapshot: Record<string, unknown>;
  reportContent: AssessmentReportContent;
  versions: AssessmentReportVersion[];
}
