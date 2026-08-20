import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiCareRepository } from '@/lib/repositories/apiRepository';
import { MockCareRepository } from '@/lib/repositories/mockRepository';

function okResponse(data: unknown) {
  return new Response(
    JSON.stringify({ code: 'OK', message: '成功', data }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}

const nursingPlanDto = {
  id: 10,
  task_id: 111,
  plan_no: 'PLAN-111',
  plan_status: 'ai_draft',
  risk_summary: '跌倒风险较高',
  education_summary: '加强防跌倒宣教',
  handover_summary: '交接步态和陪护情况',
  generated_by: 'ai:qwen',
  confirmed_by: null,
  confirmed_at: null,
  profile: {
    id: 20,
    profile_no: 'PROFILE-111',
    source_submission_ids: [30],
    cooperation_level: 'good',
    cognition_level: 'clear',
    self_care_level: 'partial_assistance',
    fall_risk_level: 'high',
    pressure_risk_level: 'medium',
    nutrition_risk_level: 'low',
    communication_level: 'good',
    education_need_level: 'high',
    profile_detail: { summary: '需要陪同下床' },
    generated_by: 'ai:qwen',
    generated_at: '2026-08-20T08:00:00Z',
  },
  items: [
    {
      id: 40,
      item_type: 'observation',
      item_code: 'fall_observation',
      item_content: '观察步态',
      source_type: 'assessment_score',
      source_id: '1',
      priority: 'high',
      nurse_action: 'pending',
      nurse_comment: null,
    },
  ],
};

describe('nursing plan repository', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('映射护理计划并按后端字段保存护士处置', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse(nursingPlanDto))
      .mockResolvedValueOnce(
        okResponse({
          ...nursingPlanDto,
          plan_status: 'adjusted',
          items: [
            {
              ...nursingPlanDto.items[0],
              nurse_action: 'accepted',
            },
          ],
        })
      );
    vi.stubGlobal('fetch', fetchMock);
    const repository = new ApiCareRepository();

    const plan = await repository.getNursingPlan('111');
    expect(plan?.profile.fallRiskLevel).toBe('high');
    expect(plan?.items[0].nurseAction).toBe('pending');

    await repository.updateNursingPlan('111', {
      riskSummary: plan!.riskSummary,
      educationSummary: plan!.educationSummary,
      handoverSummary: plan!.handoverSummary,
      items: [
        {
          id: 40,
          itemContent: '观察步态并陪同下床',
          priority: 'high',
          nurseAction: 'accepted',
          nurseComment: '已核对',
        },
      ],
    });

    const request = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      risk_summary: '跌倒风险较高',
      items: [
        {
          id: 40,
          item_content: '观察步态并陪同下床',
          nurse_action: 'accepted',
          nurse_comment: '已核对',
        },
      ],
    });
  });

  it('Mock 模式支持生成、修改和确认护理计划闭环', async () => {
    const repository = new MockCareRepository();
    const generated = await repository.generateNursingPlan('demo-1');
    expect(generated.items.length).toBeGreaterThan(0);

    const adjusted = await repository.updateNursingPlan('demo-1', {
      riskSummary: generated.riskSummary,
      educationSummary: generated.educationSummary,
      handoverSummary: generated.handoverSummary,
      items: generated.items.map((item) => ({
        id: item.id,
        itemContent: item.itemContent,
        priority: item.priority,
        nurseAction: 'accepted',
        nurseComment: null,
      })),
    });
    const confirmed = await repository.confirmNursingPlan('demo-1');

    expect(adjusted.planStatus).toBe('adjusted');
    expect(confirmed.planStatus).toBe('confirmed');
  });
});
