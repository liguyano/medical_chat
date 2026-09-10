import { describe, expect, it } from 'vitest';
import { mapExtractedField } from '@/lib/api/mappers';

describe('固定人工审核字段映射', () => {
  it('保留后端 collection_status，使患者和护士端能区分人工审核状态', () => {
    const answer = mapExtractedField({
      question_id: 21,
      question_code: 'outdoor_night_lighting',
      question_text: '夜间路灯和楼道照明良好',
      answer_type: 'boolean',
      options: [],
      source_message_ids: [],
      confidence: 0,
      corrected: false,
      collection_status: 'manual_review_pending',
    } as Parameters<typeof mapExtractedField>[0] & {
      collection_status: 'manual_review_pending';
    });

    expect(answer.collectionStatus).toBe('manual_review_pending');
  });
});
