import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';

function okResponse(data: unknown) {
  return new Response(
    JSON.stringify({ code: 'OK', message: '成功', data }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}

describe('quality repository', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('提交逐条质评时发送评分、标签、备注和护士ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(null));
    vi.stubGlobal('fetch', fetchMock);

    await new ApiCareRepository().submitMessageFeedback({
      taskId: '3',
      messageId: 'MSG-1',
      reviewerId: 'N001',
      feedbackType: 'dislike',
      score: 2,
      issueTags: ['追问不合理'],
      comment: '应先确认持续时间',
      reviewedAt: '2026-08-18T10:00:00Z',
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      task_id: '3',
      message_id: 'MSG-1',
      reviewer_id: 1,
      rating: 'dislike',
      score: 2,
      issue_tags: ['追问不合理'],
      comment: '应先确认持续时间',
    });
  });

  it('读取并映射整体质量评价', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        okResponse({
          task_id: 3,
          reviewer_id: 1,
          dialogue_scores: { 追问合理性: 4 },
          assessment_scores: { 答案完整性: 5 },
          submitted_at: '2026-08-18T11:00:00Z',
        })
      )
    );

    const review = await new ApiCareRepository().getQualityReview('3', 'N001');
    expect(review?.taskId).toBe('3');
    expect(review?.dialogueScores['追问合理性']).toBe(4);
  });
});
