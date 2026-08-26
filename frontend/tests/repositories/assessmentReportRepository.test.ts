import { describe, expect, it } from 'vitest';
import { MockCareRepository } from '@/lib/repositories/mockRepository';

describe('MockCareRepository assessment report', () => {
  it('keeps report history when regenerating', async () => {
    const repository = new MockCareRepository();
    const taskId = `report-${Date.now()}`;

    const first = await repository.generateAssessmentReport(taskId);
    const second = await repository.generateAssessmentReport(taskId, true);
    const historical = await repository.getAssessmentReport(taskId, first.versionNo);

    expect(second.versionNo).toBe(first.versionNo + 1);
    expect(second.versions.map((item) => item.versionNo)).toEqual([
      second.versionNo,
      first.versionNo,
    ]);
    expect(historical?.reportNo).toBe(first.reportNo);
  });
});
