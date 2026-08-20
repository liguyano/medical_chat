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

describe('system config repository', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('映射宣教材料并按后端字段提交直接更新', async () => {
    const dto = {
      id: 1,
      version_id: 2,
      unit_id: 3,
      category: 'allergy',
      title: '药物过敏宣教',
      document_version: '1.0',
      original_content: '原文',
      patient_content: '患者文本',
      spoken_content: '播报文本',
      source_name: '演示材料',
      priority: 'high',
      requires_acknowledgement: true,
      auto_play: true,
      enabled: true,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse([dto]))
      .mockResolvedValueOnce(
        okResponse({ ...dto, patient_content: '修改后的患者文本' })
      );
    vi.stubGlobal('fetch', fetchMock);
    const repository = new ApiCareRepository();

    const [material] = await repository.listEducationMaterials();
    expect(material.id).toBe('1');
    expect(material.patientContent).toBe('患者文本');

    await repository.updateEducationMaterial('1', {
      title: material.title,
      documentVersion: material.documentVersion,
      originalContent: material.originalContent,
      patientContent: '修改后的患者文本',
      spokenContent: material.spokenContent,
      sourceName: material.sourceName,
      priority: material.priority,
      requiresAcknowledgement: material.requiresAcknowledgement,
      autoPlay: material.autoPlay,
      enabled: material.enabled,
    });

    const request = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      patient_content: '修改后的患者文本',
      requires_acknowledgement: true,
      auto_play: true,
    });
  });

  it('提交规则命中测试并映射命中结果', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse([
        {
          rule_code: 'allergy_risk',
          rule_name: '药物过敏',
          matched_terms: ['青霉素过敏'],
          action_type: 'constraint_prompt',
          prompt: '追问过敏反应',
          priority: 100,
        },
      ])
    );
    vi.stubGlobal('fetch', fetchMock);

    const matches = await new ApiCareRepository().testInteractionRules(
      '我对青霉素过敏'
    );

    expect(matches[0]).toMatchObject({
      ruleCode: 'allergy_risk',
      matchedTerms: ['青霉素过敏'],
    });
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      text: '我对青霉素过敏',
    });
  });

  it('Mock 模式可查看并更新三个配置域', async () => {
    const repository = new MockCareRepository();
    const materials = await repository.listEducationMaterials();
    const rules = await repository.listInteractionRules();
    const scales = await repository.listScaleConfigs();

    const saved = await repository.updateEducationMaterial(materials[0].id, {
      ...materials[0],
      title: '修改后的演示材料',
    });
    const detail = await repository.getScaleConfig(scales[0].id);

    expect(saved.title).toBe('修改后的演示材料');
    expect(rules.length).toBeGreaterThan(0);
    expect(detail.scale_code).toBe(scales[0].scaleCode);
  });
});
