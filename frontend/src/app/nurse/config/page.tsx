'use client';

import { FormEvent, useEffect, useState } from 'react';
import {
  BookOpenIcon,
  CheckCircleIcon,
  DocumentCheckIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';

import NurseLayout from '@/components/layout/NurseLayout';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card } from '@/components/shared/Card';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import { useUserStore } from '@/lib/stores/useUserStore';
import type {
  AssessmentScaleConfigDetail,
  AssessmentScaleConfigSummary,
  EducationMaterialConfig,
  InteractionRuleConfig,
  InteractionRuleMatch,
} from '@/lib/types';
import { cn } from '@/lib/utils';

type ConfigTab = 'education' | 'rules' | 'scales';

const tabs: Array<{
  id: ConfigTab;
  label: string;
  description: string;
  icon: typeof BookOpenIcon;
}> = [
  {
    id: 'education',
    label: '宣教材料',
    description: '患者可见与播报内容',
    icon: BookOpenIcon,
  },
  {
    id: 'rules',
    label: '拦截特征字典',
    description: '关键词、正则与约束提示',
    icon: FunnelIcon,
  },
  {
    id: 'scales',
    label: '评估量表',
    description: '查看并编辑全部配置项',
    icon: DocumentCheckIcon,
  },
];

const fieldClass =
  'w-full rounded-xl border border-border bg-white px-3 py-2.5 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15';
const labelClass = 'mb-1.5 block text-sm font-medium text-foreground';

function linesToList(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item, index, all) => item && all.indexOf(item) === index);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试';
}

export default function NurseConfigPage() {
  const isAuthenticated = useUserStore((state) => state.isAuthenticated);
  const [activeTab, setActiveTab] = useState<ConfigTab>('education');
  const [materials, setMaterials] = useState<EducationMaterialConfig[]>([]);
  const [selectedMaterialId, setSelectedMaterialId] = useState('');
  const [materialDraft, setMaterialDraft] =
    useState<EducationMaterialConfig | null>(null);
  const [rules, setRules] = useState<InteractionRuleConfig[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState('');
  const [ruleDraft, setRuleDraft] = useState<InteractionRuleConfig | null>(
    null
  );
  const [testText, setTestText] = useState('');
  const [testMatches, setTestMatches] = useState<InteractionRuleMatch[]>([]);
  const [scaleSummaries, setScaleSummaries] = useState<
    AssessmentScaleConfigSummary[]
  >([]);
  const [selectedScaleId, setSelectedScaleId] = useState('');
  const [scaleJson, setScaleJson] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    void Promise.all([
      careRepository.listEducationMaterials(controller.signal),
      careRepository.listInteractionRules(controller.signal),
      careRepository.listScaleConfigs(controller.signal),
    ])
      .then(async ([materialItems, ruleItems, summaries]) => {
        setMaterials(materialItems);
        setRules(ruleItems);
        setScaleSummaries(summaries);
        if (materialItems[0]) {
          setSelectedMaterialId(materialItems[0].id);
          setMaterialDraft(structuredClone(materialItems[0]));
        }
        if (ruleItems[0]) {
          setSelectedRuleId(ruleItems[0].id);
          setRuleDraft(structuredClone(ruleItems[0]));
        }
        if (summaries[0]) {
          setSelectedScaleId(summaries[0].id);
          const detail = await careRepository.getScaleConfig(
            summaries[0].id,
            controller.signal
          );
          setScaleJson(JSON.stringify(detail, null, 2));
        }
      })
      .catch((reason) => {
        if (!isRequestCancelled(reason)) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => abortRequest(controller);
  }, [isAuthenticated]);

  const selectMaterial = (item: EducationMaterialConfig) => {
    setSelectedMaterialId(item.id);
    setMaterialDraft(structuredClone(item));
    setError('');
    setMessage('');
  };

  const selectRule = (item: InteractionRuleConfig) => {
    setSelectedRuleId(item.id);
    setRuleDraft(structuredClone(item));
    setTestMatches([]);
    setError('');
    setMessage('');
  };

  const selectScale = async (item: AssessmentScaleConfigSummary) => {
    setSelectedScaleId(item.id);
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const detail = await careRepository.getScaleConfig(item.id);
      setScaleJson(JSON.stringify(detail, null, 2));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  };

  const saveMaterial = async (event: FormEvent) => {
    event.preventDefault();
    if (!materialDraft) return;
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await careRepository.updateEducationMaterial(
        selectedMaterialId,
        {
          title: materialDraft.title,
          documentVersion: materialDraft.documentVersion,
          originalContent: materialDraft.originalContent,
          patientContent: materialDraft.patientContent,
          spokenContent: materialDraft.spokenContent,
          sourceName: materialDraft.sourceName,
          priority: materialDraft.priority,
          requiresAcknowledgement:
            materialDraft.requiresAcknowledgement,
          autoPlay: materialDraft.autoPlay,
          enabled: materialDraft.enabled,
        }
      );
      setMaterials((items) =>
        items.map((item) => (item.id === saved.id ? saved : item))
      );
      setMaterialDraft(saved);
      setMessage('宣教材料已保存，新触发的宣教将立即使用该内容。');
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  };

  const saveRule = async (event: FormEvent) => {
    event.preventDefault();
    if (!ruleDraft) return;
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await careRepository.updateInteractionRule(
        selectedRuleId,
        {
          ruleName: ruleDraft.ruleName,
          scopeType: ruleDraft.scopeType,
          scopeId: ruleDraft.scopeId,
          keywords: ruleDraft.keywords,
          patterns: ruleDraft.patterns,
          actionType: ruleDraft.actionType,
          prompt: ruleDraft.prompt,
          tags: ruleDraft.tags,
          priority: ruleDraft.priority,
          enabled: ruleDraft.enabled,
        }
      );
      setRules((items) =>
        items.map((item) => (item.id === saved.id ? saved : item))
      );
      setRuleDraft(saved);
      setMessage('拦截规则已保存并立即生效。');
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  };

  const runRuleTest = async () => {
    if (!testText.trim()) {
      setError('请输入需要测试的患者表达。');
      return;
    }
    setTesting(true);
    setError('');
    try {
      setTestMatches(await careRepository.testInteractionRules(testText));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setTesting(false);
    }
  };

  const saveScale = async () => {
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const parsed = JSON.parse(scaleJson) as AssessmentScaleConfigDetail;
      if (String(parsed.id) !== selectedScaleId) {
        throw new Error('JSON 中的量表编号与当前选择不一致');
      }
      const saved = await careRepository.updateScaleConfig(
        selectedScaleId,
        parsed
      );
      setScaleJson(JSON.stringify(saved, null, 2));
      setScaleSummaries((items) =>
        items.map((item) =>
          item.id === selectedScaleId
            ? {
                ...item,
                scaleName: saved.scale_name,
                scaleType: saved.scale_type,
                clinicalPurpose: saved.clinical_purpose ?? undefined,
                status: saved.status,
                versionName: saved.version_name,
                publishStatus: saved.publish_status,
                sectionCount: saved.sections.length,
                questionCount: saved.questions.length,
                optionCount: saved.options.length,
                ruleCount: saved.rules.length,
                actionCount: saved.actions.length,
              }
            : item
        )
      );
      setMessage('量表配置已保存并立即生效。');
    } catch (reason) {
      setError(
        reason instanceof SyntaxError
          ? 'JSON 格式错误，请检查逗号、引号和括号。'
          : errorMessage(reason)
      );
    } finally {
      setSaving(false);
    }
  };

  const selectedScale = scaleSummaries.find(
    (item) => item.id === selectedScaleId
  );

  return (
    <NurseLayout wide>
      <div className="mb-6">
        <Badge variant="primary">Demo 配置中心</Badge>
        <h1 className="mt-2 text-3xl">
          系统<span className="text-primary italic">配置</span>
        </h1>
        <p className="mt-1 text-foreground-muted">
          登录医护可直接查看和修改，保存后立即生效。
        </p>
      </div>

      <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => {
              setActiveTab(tab.id);
              setError('');
              setMessage('');
            }}
            className={cn(
              'flex items-center gap-3 rounded-2xl border p-4 text-left transition',
              activeTab === tab.id
                ? 'border-primary bg-primary-tint text-primary'
                : 'border-border bg-white hover:border-primary/40'
            )}
          >
            <tab.icon className="h-6 w-6 shrink-0" />
            <span>
              <span className="block font-medium">{tab.label}</span>
              <span className="mt-0.5 block text-xs text-foreground-muted">
                {tab.description}
              </span>
            </span>
          </button>
        ))}
      </div>

      {(error || message) && (
        <div
          role="status"
          className={cn(
            'mb-5 rounded-xl border px-4 py-3 text-sm',
            error
              ? 'border-red-200 bg-red-50 text-red-700'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700'
          )}
        >
          {error || message}
        </div>
      )}

      {loading && !materialDraft ? (
        <Card padding="lg">
          <p className="text-sm text-foreground-muted">正在加载配置...</p>
        </Card>
      ) : (
        <>
          {activeTab === 'education' && materialDraft && (
            <div className="grid gap-5 xl:grid-cols-[22rem_minmax(0,1fr)]">
              <Card padding="sm">
                <h2 className="mb-3 px-1 text-lg">宣教材料列表</h2>
                <div className="space-y-2">
                  {materials.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectMaterial(item)}
                      className={cn(
                        'w-full rounded-xl border p-3 text-left',
                        item.id === selectedMaterialId
                          ? 'border-primary bg-primary-tint'
                          : 'border-transparent bg-surface-secondary'
                      )}
                    >
                      <span className="block font-medium">{item.title}</span>
                      <span className="mt-1 block text-xs text-foreground-muted">
                        {item.category} · v{item.documentVersion} ·{' '}
                        {item.enabled ? '已启用' : '已停用'}
                      </span>
                    </button>
                  ))}
                </div>
              </Card>

              <Card padding="lg">
                <form onSubmit={saveMaterial} className="space-y-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="text-xl">编辑宣教材料</h2>
                      <p className="mt-1 text-sm text-foreground-muted">
                        分类编码 {materialDraft.category} 不允许修改。
                      </p>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={materialDraft.enabled}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            enabled: event.target.checked,
                          })
                        }
                      />
                      启用
                    </label>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <label>
                      <span className={labelClass}>材料标题</span>
                      <input
                        className={fieldClass}
                        required
                        maxLength={128}
                        value={materialDraft.title}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            title: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      <span className={labelClass}>文档版本</span>
                      <input
                        className={fieldClass}
                        required
                        maxLength={64}
                        value={materialDraft.documentVersion}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            documentVersion: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      <span className={labelClass}>来源名称</span>
                      <input
                        className={fieldClass}
                        maxLength={256}
                        value={materialDraft.sourceName ?? ''}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            sourceName: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      <span className={labelClass}>优先级</span>
                      <select
                        className={fieldClass}
                        value={materialDraft.priority}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            priority: event.target.value as
                              | 'low'
                              | 'medium'
                              | 'high',
                          })
                        }
                      >
                        <option value="low">一般</option>
                        <option value="medium">重要</option>
                        <option value="high">高风险</option>
                      </select>
                    </label>
                  </div>
                  {[
                    ['originalContent', '医学宣教原文', 7],
                    ['patientContent', '患者易懂文本', 5],
                    ['spokenContent', '语音播报文本', 5],
                  ].map(([field, label, rows]) => (
                    <label key={field}>
                      <span className={labelClass}>{label}</span>
                      <textarea
                        className={fieldClass}
                        required
                        rows={Number(rows)}
                        value={
                          materialDraft[
                            field as
                              | 'originalContent'
                              | 'patientContent'
                              | 'spokenContent'
                          ]
                        }
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            [field]: event.target.value,
                          })
                        }
                      />
                    </label>
                  ))}
                  <div className="flex flex-wrap gap-5">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={materialDraft.requiresAcknowledgement}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            requiresAcknowledgement: event.target.checked,
                          })
                        }
                      />
                      需要患者确认已阅读
                    </label>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={materialDraft.autoPlay}
                        onChange={(event) =>
                          setMaterialDraft({
                            ...materialDraft,
                            autoPlay: event.target.checked,
                          })
                        }
                      />
                      触发后自动播报
                    </label>
                  </div>
                  <Button type="submit" loading={saving}>
                    保存并立即生效
                  </Button>
                </form>
              </Card>
            </div>
          )}

          {activeTab === 'rules' && ruleDraft && (
            <div className="grid gap-5 xl:grid-cols-[22rem_minmax(0,1fr)]">
              <Card padding="sm">
                <h2 className="mb-3 px-1 text-lg">拦截规则列表</h2>
                <div className="space-y-2">
                  {rules.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectRule(item)}
                      className={cn(
                        'w-full rounded-xl border p-3 text-left',
                        item.id === selectedRuleId
                          ? 'border-primary bg-primary-tint'
                          : 'border-transparent bg-surface-secondary'
                      )}
                    >
                      <span className="block font-medium">{item.ruleName}</span>
                      <span className="mt-1 block text-xs text-foreground-muted">
                        {item.ruleCode} · 优先级 {item.priority} ·{' '}
                        {item.enabled ? '已启用' : '已停用'}
                      </span>
                    </button>
                  ))}
                </div>
              </Card>

              <div className="space-y-5">
                <Card padding="lg">
                  <form onSubmit={saveRule} className="space-y-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h2 className="text-xl">编辑拦截规则</h2>
                        <p className="mt-1 text-sm text-foreground-muted">
                          规则编码 {ruleDraft.ruleCode} 不允许修改。
                        </p>
                      </div>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={ruleDraft.enabled}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              enabled: event.target.checked,
                            })
                          }
                        />
                        启用
                      </label>
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <label>
                        <span className={labelClass}>规则名称</span>
                        <input
                          className={fieldClass}
                          required
                          value={ruleDraft.ruleName}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              ruleName: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        <span className={labelClass}>优先级</span>
                        <input
                          className={fieldClass}
                          type="number"
                          min={-10000}
                          max={10000}
                          value={ruleDraft.priority}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              priority: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label>
                        <span className={labelClass}>作用范围</span>
                        <input
                          className={fieldClass}
                          required
                          value={ruleDraft.scopeType}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              scopeType: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        <span className={labelClass}>动作类型</span>
                        <input
                          className={fieldClass}
                          required
                          value={ruleDraft.actionType}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              actionType: event.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="grid gap-4 lg:grid-cols-3">
                      <label>
                        <span className={labelClass}>关键词（每行一个）</span>
                        <textarea
                          className={fieldClass}
                          rows={7}
                          value={ruleDraft.keywords.join('\n')}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              keywords: linesToList(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label>
                        <span className={labelClass}>正则（每行一个）</span>
                        <textarea
                          className={fieldClass}
                          rows={7}
                          value={ruleDraft.patterns.join('\n')}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              patterns: linesToList(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label>
                        <span className={labelClass}>标签（每行一个）</span>
                        <textarea
                          className={fieldClass}
                          rows={7}
                          value={ruleDraft.tags.join('\n')}
                          onChange={(event) =>
                            setRuleDraft({
                              ...ruleDraft,
                              tags: linesToList(event.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <label>
                      <span className={labelClass}>命中后的约束提示</span>
                      <textarea
                        className={fieldClass}
                        required
                        rows={5}
                        value={ruleDraft.prompt}
                        onChange={(event) =>
                          setRuleDraft({
                            ...ruleDraft,
                            prompt: event.target.value,
                          })
                        }
                      />
                    </label>
                    <Button type="submit" loading={saving}>
                      保存并立即生效
                    </Button>
                  </form>
                </Card>

                <Card padding="lg">
                  <h2 className="text-xl">命中测试</h2>
                  <p className="mt-1 text-sm text-foreground-muted">
                    输入一句患者表达，使用数据库中的全部启用规则测试。
                  </p>
                  <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                    <input
                      className={fieldClass}
                      placeholder="例如：我对青霉素过敏"
                      value={testText}
                      onChange={(event) => setTestText(event.target.value)}
                    />
                    <Button
                      type="button"
                      loading={testing}
                      onClick={() => void runRuleTest()}
                      className="shrink-0"
                    >
                      测试命中
                    </Button>
                  </div>
                  {testMatches.length > 0 ? (
                    <div className="mt-4 space-y-2">
                      {testMatches.map((match) => (
                        <div
                          key={match.ruleCode}
                          className="rounded-xl bg-emerald-50 p-3 text-sm"
                        >
                          <p className="font-medium text-emerald-800">
                            {match.ruleName}：{match.matchedTerms.join('、')}
                          </p>
                          <p className="mt-1 text-emerald-700">
                            {match.prompt}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    testText &&
                    !testing && (
                      <p className="mt-4 text-sm text-foreground-muted">
                        当前没有命中记录。
                      </p>
                    )
                  )}
                </Card>
              </div>
            </div>
          )}

          {activeTab === 'scales' && (
            <div className="grid gap-5 xl:grid-cols-[24rem_minmax(0,1fr)]">
              <Card padding="sm">
                <h2 className="mb-3 px-1 text-lg">评估量表列表</h2>
                <div className="space-y-2">
                  {scaleSummaries.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => void selectScale(item)}
                      className={cn(
                        'w-full rounded-xl border p-3 text-left',
                        item.id === selectedScaleId
                          ? 'border-primary bg-primary-tint'
                          : 'border-transparent bg-surface-secondary'
                      )}
                    >
                      <span className="block font-medium">
                        {item.scaleName}
                      </span>
                      <span className="mt-1 block text-xs text-foreground-muted">
                        {item.scaleCode} · v{item.versionCode}
                      </span>
                      <span className="mt-2 block text-xs text-foreground-muted">
                        {item.sectionCount} 分组 / {item.questionCount} 题目 /{' '}
                        {item.optionCount} 选项 / {item.ruleCount} 规则 /{' '}
                        {item.actionCount} 措施
                      </span>
                    </button>
                  ))}
                </div>
              </Card>

              <Card padding="lg">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-xl">
                      {selectedScale?.scaleName ?? '量表完整配置'}
                    </h2>
                    <p className="mt-1 text-sm text-foreground-muted">
                      JSON 包含量表主档、版本、分组、题目、选项、规则和护理措施。
                      Demo 模式只允许编辑已有记录，不允许在此新增或删除配置项。
                    </p>
                  </div>
                  {selectedScale && (
                    <Badge variant="success">
                      {selectedScale.publishStatus}
                    </Badge>
                  )}
                </div>
                <textarea
                  aria-label="量表完整 JSON 配置"
                  spellCheck={false}
                  className={cn(
                    fieldClass,
                    'mt-5 min-h-[34rem] resize-y font-mono text-xs leading-5'
                  )}
                  value={scaleJson}
                  onChange={(event) => setScaleJson(event.target.value)}
                />
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button
                    type="button"
                    loading={saving}
                    onClick={() => void saveScale()}
                  >
                    保存并立即生效
                  </Button>
                  <span className="flex items-center gap-1 text-xs text-foreground-muted">
                    <CheckCircleIcon className="h-4 w-4" />
                    后端会校验编号关联和字段类型
                  </span>
                </div>
              </Card>
            </div>
          )}
        </>
      )}
    </NurseLayout>
  );
}
