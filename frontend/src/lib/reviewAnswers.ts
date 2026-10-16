/** 合并逐题修改；未修改答案保留原值，撤销修改后不携带旧原因。 */
export function buildReviewAnswers(
  questionIds: string[],
  sourceAnswers: Record<string, string>,
  nurseAnswers: Record<string, string>,
  reasons: Record<string, string>
) {
  const answers = { ...sourceAnswers, ...nurseAnswers };
  const changedIds = questionIds.filter(
    (id) => (answers[id] ?? '') !== (sourceAnswers[id] ?? '')
  );
  const correctionReasons = Object.fromEntries(
    changedIds
      .filter((id) => reasons[id]?.trim())
      .map((id) => [id, reasons[id].trim()])
  );
  return { answers, changedIds, correctionReasons };
}
