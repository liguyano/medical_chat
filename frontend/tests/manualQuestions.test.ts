import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { mapExtractedField, mapQuestionnaireDto } from '@/lib/api/mappers';
import { getStructuredAnswerDisplayValue } from '@/lib/structuredAnswer';
import { RecordedAnswersPanel } from '@/components/patient/RecordedAnswersPanel';
import QuestionCard from '@/components/assessment/QuestionCard';
import type { QuestionnaireDto } from '@/lib/api/contracts';

const field = { question_id: 1, question_code: 'Q', question_text: '人工测量', manual_required: true };
describe('人工题元数据与真实答案', () => {
  it('映射人工标记且不生成答案', () => {
    const answer = mapExtractedField(field);
    expect(answer).toMatchObject({ manualRequired: true });
    expect(answer.answerText).toBeUndefined();
    expect(answer.displayValue).toBeUndefined();
    expect(getStructuredAnswerDisplayValue(answer)).toBe('等待人工');
    expect(mapExtractedField({ ...field, manual_required: undefined })).toMatchObject({ manualRequired: false });
  });
  it('护士已填零和否保留真实值', () => {
    expect(getStructuredAnswerDisplayValue(mapExtractedField({ ...field, answer_number: 0 }))).toBe('0');
    expect(getStructuredAnswerDisplayValue(mapExtractedField({ ...field, answer_boolean: false }))).toBe('否');
  });
  it('侧栏分开计数并展示等待状态', () => {
    const html = renderToStaticMarkup(createElement(RecordedAnswersPanel, { answers: [mapExtractedField(field)] }));
    expect(html).toContain('等待人工');
    expect(html).toMatch(/当前已记录 <strong[^>]*>0<\/strong>/);
    expect(html).toContain('等待人工 1 项');
  });
  it('问卷映射人工标记且卡片不渲染输入', () => {
    const dto = { task_id: 1, task_no: 'T', status: 'not_started', questions: [{ id: 1, question_code: 'Q', question_text: '人工测量', question_type: 'number', required: true, derived: false, scored: false, manual_required: true, sort_no: 1 }], answers: [], scores: [] } as unknown as QuestionnaireDto;
    const question = mapQuestionnaireDto(dto).questions[0];
    expect(question).toMatchObject({ manualRequired: true });
    const html = renderToStaticMarkup(createElement(QuestionCard, { question, onChange: () => {}, animate: false }));
    expect(html).toContain('等待人工');
    expect(html).not.toContain('<input');
  });
});
