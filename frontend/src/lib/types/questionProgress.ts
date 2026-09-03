export interface QuestionProgress {
  sessionId: string;
  current: number;
  total: number;
  turnNumber: number;
  activeQuestionId: string | null;
  candidateQuestionIds: string[];
  questions: Array<{
    questionId: string;
    questionCode: string;
    questionText: string;
    scaleName: string;
    required: boolean;
    status: 'unasked' | 'asked' | 'recorded';
    isCurrent: boolean;
    coolingUntilTurn: number | null;
  }>;
}
