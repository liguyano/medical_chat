import { describe, expect, it } from 'vitest';
import { buildCgaReportSections, getAssessmentScales } from '@/lib/assessmentReportView';
import { fullCgaDemoReport } from '@/lib/demo/fullCgaReport';

describe('full CGA report demo', () => {
  it('fills every fixed CGA catalogue item with a completed assessment', () => {
    const sections = buildCgaReportSections(getAssessmentScales(fullCgaDemoReport));
    const fixedRows = sections
      .filter((section) => section.id !== 'other-completed')
      .flatMap((section) => section.rows);

    expect(fixedRows).toHaveLength(27);
    expect(fixedRows.every((row) => row.completed)).toBe(true);
    expect(fixedRows.every((row) => row.result !== '未进行相关量表')).toBe(true);
    expect(fixedRows.every((row) => row.assessor === '李护士')).toBe(true);
    expect(fixedRows.every((row) => Boolean(row.assessedAt))).toBe(true);
    expect(sections.some((section) => section.id === 'other-completed')).toBe(false);
  });

  it('provides original question details for every demonstrated scale', () => {
    const scales = getAssessmentScales(fullCgaDemoReport);

    expect(scales).toHaveLength(27);
    expect(scales.every((scale) => scale.score_status === 'complete')).toBe(true);
    expect(scales.every((scale) => (scale.answers?.length ?? 0) > 0)).toBe(true);
    expect(scales.every((scale) => (scale.scores?.length ?? 0) > 0)).toBe(true);
  });

  it('uses clearly fictitious, confirmed demonstration data', () => {
    expect(fullCgaDemoReport.reportStatus).toBe('confirmed');
    expect(fullCgaDemoReport.reportNo).toContain('DEMO');
    expect(fullCgaDemoReport.sourceSnapshot.patient).toMatchObject({
      name: '林安华（演示）',
      age: 76,
    });
  });
});
