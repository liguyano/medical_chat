'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/shared/Card';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { getTaskById } from '@/lib/mock/data';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type {
  CareTask,
  NursingPlan,
  NursingPlanAction,
  NursingPlanPriority,
} from '@/lib/types';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ClipboardDocumentListIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

const profileLabels: Array<[keyof NursingPlan['profile'], string]> = [
  ['cooperationLevel', '配合度'],
  ['cognitionLevel', '认知度'],
  ['selfCareLevel', '自理能力'],
  ['fallRiskLevel', '跌倒风险'],
  ['pressureRiskLevel', '压疮风险'],
  ['nutritionRiskLevel', '营养风险'],
  ['communicationLevel', '沟通能力'],
  ['educationNeedLevel', '宣教需求'],
];

const valueLabels: Record<string, string> = {
  good: '良好',
  partial: '一般',
  poor: '较差',
  clear: '清晰',
  mild_impairment: '轻度受损',
  impaired: '受损',
  independent: '可自理',
  partial_assistance: '部分协助',
  dependent: '依赖照护',
  low: '低',
  medium: '中',
  high: '高',
  unknown: '未知',
  limited: '受限',
  difficult: '困难',
};

const actionLabels: Record<NursingPlanAction, string> = {
  pending: '待处理',
  accepted: '接受',
  modified: '已修改',
  rejected: '拒绝',
};

const itemTypeLabels: Record<string, string> = {
  nursing_measure: '护理措施',
  education: '宣教措施',
  observation: '观察重点',
  handover: '交接班提示',
};

function statusLabel(status: string) {
  return {
    ai_draft: 'AI草案',
    adjusted: '护士已调整',
    confirmed: '已确认生效',
    ended: '已结束',
  }[status] ?? status;
}

function actionVariant(action: NursingPlanAction) {
  if (action === 'accepted') return 'success' as const;
  if (action === 'modified') return 'info' as const;
  if (action === 'rejected') return 'danger' as const;
  return 'warning' as const;
}

export default function NursingPlanPage() {
  const { id: taskId } = useParams<{ id: string }>();
  const router = useRouter();
  const storedTask = useTaskStore((state) =>
    state.tasks.find((item) => item.id === taskId)
  );
  const addTask = useTaskStore((state) => state.addTask);
  const [task, setTask] = useState<CareTask | null>(
    storedTask ??
      (runtimeConfig.dataMode === 'mock' ? getTaskById(taskId) ?? null : null)
  );
  const [plan, setPlan] = useState<NursingPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    const timer = globalThis.setTimeout(() => {
      void Promise.all([
        runtimeConfig.dataMode === 'api'
          ? careRepository.getTask(taskId, controller.signal)
          : Promise.resolve(null),
        careRepository.getNursingPlan(taskId, controller.signal),
      ])
        .then(([loadedTask, loadedPlan]) => {
          if (loadedTask) {
            setTask(loadedTask);
            addTask(loadedTask);
          }
          setError('');
          setPlan(loadedPlan);
        })
        .catch((loadError) => {
          if (controller.signal.aborted || isRequestCancelled(loadError)) return;
          setError(
            loadError instanceof Error ? loadError.message : '护理计划加载失败'
          );
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 0);
    return () => {
      globalThis.clearTimeout(timer);
      abortRequest(controller);
    };
  }, [addTask, taskId]);

  const updatePlan = (next: Partial<NursingPlan>) => {
    setPlan((current) => (current ? { ...current, ...next } : current));
  };

  const updateItem = (
    itemId: number,
    patch: Partial<NursingPlan['items'][number]>
  ) => {
    setPlan((current) =>
      current
        ? {
            ...current,
            items: current.items.map((item) =>
              item.id === itemId ? { ...item, ...patch } : item
            ),
          }
        : current
    );
  };

  const run = async (action: () => Promise<NursingPlan>, success: string) => {
    setWorking(true);
    setError('');
    setNotice('');
    try {
      setPlan(await action());
      setNotice(success);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : '操作失败');
    } finally {
      setWorking(false);
    }
  };

  const generate = (force = false) =>
    run(
      () => careRepository.generateNursingPlan(taskId, force),
      force ? '已重新生成 AI 护理计划草案' : '已生成 AI 护理计划草案'
    );

  const save = () => {
    if (!plan) return Promise.resolve();
    return run(
      () =>
        careRepository.updateNursingPlan(taskId, {
          riskSummary: plan.riskSummary,
          educationSummary: plan.educationSummary,
          handoverSummary: plan.handoverSummary,
          items: plan.items.map((item) => ({
            id: item.id,
            itemContent: item.itemContent,
            priority: item.priority,
            nurseAction: item.nurseAction,
            nurseComment: item.nurseComment ?? null,
          })),
        }),
      '护士修改已保存'
    );
  };

  const confirm = () =>
    run(() => careRepository.confirmNursingPlan(taskId), '护理计划已确认生效');

  const pendingCount = useMemo(
    () => plan?.items.filter((item) => item.nurseAction === 'pending').length ?? 0,
    [plan]
  );

  if (loading && !plan) {
    return (
      <NurseLayout>
        <div className="py-20 text-center text-foreground-muted">正在加载患者画像与护理计划...</div>
      </NurseLayout>
    );
  }

  return (
    <NurseLayout>
      <div className="max-w-6xl mx-auto space-y-5">
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-2 text-sm text-foreground-muted hover:text-foreground"
        >
          <ArrowLeftIcon className="w-4 h-4" /> 返回任务详情
        </button>

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
          <div>
            <p className="text-sm text-foreground-muted">
              {task?.patientName ?? '患者'} · {task?.bedNo ?? '床位未知'} · {task?.taskNo ?? taskId}
            </p>
            <h1 className="text-3xl font-serif font-medium mt-1">
              患者<span className="text-primary italic">画像与护理计划</span>
            </h1>
            <p className="text-sm text-foreground-muted mt-2">
              AI 根据评估答案、量表风险和对话摘要形成差异化建议，护士编辑并确认后生效。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {plan && <Badge variant={plan.planStatus === 'confirmed' ? 'success' : 'primary'}>{statusLabel(plan.planStatus)}</Badge>}
            <Badge variant="info">{runtimeConfig.dataMode === 'api' ? 'API 已连接' : 'Mock 演示'}</Badge>
          </div>
        </div>

        {error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        {notice && <div className="rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-700">{notice}</div>}

        {!plan ? (
          <Card padding="lg" className="text-center">
            <SparklesIcon className="w-12 h-12 mx-auto text-primary mb-3" />
            <h2 className="text-xl font-semibold">尚未生成护理计划</h2>
            <p className="text-sm text-foreground-muted mt-2">
              评估完成后可根据结构化结果生成 AI 患者画像和护理指导草案。
            </p>
            <Button className="mt-5" loading={working} onClick={() => void generate()}>
              <SparklesIcon className="w-4 h-4 mr-2" /> 生成 AI 草案
            </Button>
          </Card>
        ) : (
          <>
            <Card padding="lg">
              <CardHeader>
                <CardTitle>患者画像</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {profileLabels.map(([key, label]) => (
                    <div key={key} className="rounded-xl bg-surface-secondary p-4">
                      <p className="text-xs text-foreground-muted">{label}</p>
                      <p className="font-semibold mt-1">
                        {valueLabels[String(plan.profile[key])] ?? String(plan.profile[key])}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-xl border border-primary/20 bg-primary-tint p-4">
                  <p className="text-xs text-primary font-medium">画像摘要</p>
                  <p className="text-sm leading-6 mt-1">
                    {String(plan.profile.detail.summary ?? '暂无摘要')}
                  </p>
                  {!!plan.profile.detail.evidence && (
                    <p className="text-xs text-foreground-muted mt-2">
                      来源：{(plan.profile.detail.evidence as string[]).join('、')}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card padding="lg">
              <CardHeader>
                <CardTitle>护理计划摘要</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  {(
                    [
                      ['riskSummary', '风险摘要'],
                      ['educationSummary', '宣教重点'],
                      ['handoverSummary', '交接班重点'],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key} className="text-sm font-medium">
                      {label}
                      <textarea
                        rows={5}
                        value={plan[key]}
                        disabled={plan.planStatus === 'confirmed'}
                        onChange={(event) => updatePlan({ [key]: event.target.value })}
                        className="w-full mt-2 rounded-xl border border-border bg-surface px-3 py-2.5 text-sm font-normal focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:bg-surface-secondary"
                      />
                    </label>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card padding="lg">
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <CardTitle>差异化护理指导</CardTitle>
                  <span className="text-xs text-foreground-muted">
                    {pendingCount ? `还有 ${pendingCount} 项待护士处理` : '所有建议已处理'}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {plan.items.map((item, index) => (
                    <div key={item.id} className="rounded-xl border border-border p-4">
                      <div className="flex flex-col lg:flex-row lg:items-start gap-3">
                        <div className="flex-1">
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <span className="text-xs text-foreground-muted">建议 {index + 1}</span>
                            <Badge size="sm">{itemTypeLabels[item.itemType] ?? item.itemType}</Badge>
                            <Badge size="sm" variant={actionVariant(item.nurseAction)}>
                              {actionLabels[item.nurseAction]}
                            </Badge>
                            <span className="text-xs text-foreground-muted">来源：{item.sourceType}</span>
                          </div>
                          <textarea
                            rows={3}
                            value={item.itemContent}
                            disabled={plan.planStatus === 'confirmed'}
                            onChange={(event) => updateItem(item.id, { itemContent: event.target.value, nurseAction: 'modified' })}
                            className="w-full rounded-xl border border-border bg-surface px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:bg-surface-secondary"
                          />
                        </div>
                        <div className="w-full lg:w-56 space-y-2">
                          <label className="text-xs text-foreground-muted">
                            优先级
                            <select
                              value={item.priority}
                              disabled={plan.planStatus === 'confirmed'}
                              onChange={(event) => updateItem(item.id, { priority: event.target.value as NursingPlanPriority, nurseAction: 'modified' })}
                              className="w-full mt-1 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm"
                            >
                              <option value="high">高</option>
                              <option value="medium">中</option>
                              <option value="low">低</option>
                            </select>
                          </label>
                          <label className="text-xs text-foreground-muted">
                            护士处置
                            <select
                              value={item.nurseAction}
                              disabled={plan.planStatus === 'confirmed'}
                              onChange={(event) => updateItem(item.id, { nurseAction: event.target.value as NursingPlanAction })}
                              className="w-full mt-1 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm"
                            >
                              {Object.entries(actionLabels).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                            </select>
                          </label>
                          <input
                            value={item.nurseComment ?? ''}
                            disabled={plan.planStatus === 'confirmed'}
                            onChange={(event) => updateItem(item.id, { nurseComment: event.target.value })}
                            placeholder="护士备注（可选）"
                            className="w-full rounded-lg border border-border bg-surface px-2.5 py-2 text-sm disabled:bg-surface-secondary"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="flex flex-col sm:flex-row sm:justify-end gap-3">
              <Button
                variant="outline"
                disabled={working || plan.planStatus === 'confirmed'}
                onClick={() => void generate(true)}
              >
                <ArrowPathIcon className="w-4 h-4 mr-2" /> 重新生成
              </Button>
              <Button
                variant="secondary"
                disabled={working || plan.planStatus === 'confirmed'}
                onClick={() => void save()}
              >
                <ClipboardDocumentListIcon className="w-4 h-4 mr-2" /> 保存护士修改
              </Button>
              <Button
                loading={working}
                disabled={plan.planStatus === 'confirmed' || pendingCount > 0}
                onClick={() => void confirm()}
              >
                <CheckCircleIcon className="w-4 h-4 mr-2" /> 确认护理计划
              </Button>
            </div>
          </>
        )}
      </div>
    </NurseLayout>
  );
}
