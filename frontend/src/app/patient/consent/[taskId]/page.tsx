'use client';

import { useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import SignaturePad from '@/components/consent/SignaturePad';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { careRepository } from '@/lib/repositories';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { applyRealtimeEvent } from '@/lib/transports/applyRealtimeEvent';
import { toHandoffSseEnvelope } from '@/lib/transports/handoffResponse';
import type { ConsentClause, ConsentProgress } from '@/lib/types';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  SpeakerWaveIcon,
} from '@heroicons/react/24/outline';

const initialClauses: ConsentClause[] = [
  {
    id: 'consent-1',
    clauseCode: 'IDENTITY',
    clauseName: '身份与信息核对',
    patientContent: '检查、治疗和用药前，医护人员会核对您的姓名、腕带和住院信息，请您主动配合。',
    importanceLevel: 'important',
    mandatoryDelivery: true,
    explicitConfirmationRequired: true,
    deliveryStatus: 'pending',
    listened: false,
    confirmed: false,
  },
  {
    id: 'consent-2',
    clauseCode: 'SAFETY',
    clauseName: '护理安全',
    patientContent: '如您行动不便、头晕或夜间需要下床，请先使用呼叫铃，不要独自下床。',
    importanceLevel: 'critical',
    mandatoryDelivery: true,
    explicitConfirmationRequired: true,
    deliveryStatus: 'pending',
    listened: false,
    confirmed: false,
  },
  {
    id: 'consent-3',
    clauseCode: 'PRIVACY',
    clauseName: '隐私与数据使用',
    patientContent: '本次回答用于护理评估，AI整理结果必须由护士复核。原型中不会上传真实患者信息。',
    importanceLevel: 'important',
    mandatoryDelivery: true,
    explicitConfirmationRequired: true,
    deliveryStatus: 'pending',
    listened: false,
    confirmed: false,
  },
];

export default function PatientConsentPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const savedConsent = useTaskStore((state) => state.consents[taskId]);
  const saveConsent = useTaskStore((state) => state.saveConsent);
  const updateTask = useTaskStore((state) => state.updateTask);
  const [clauses, setClauses] = useState(savedConsent?.clauses ?? initialClauses);
  const [signatureData, setSignatureData] = useState(savedConsent?.signatureData);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const completedCount = clauses.filter((clause) => clause.confirmed).length;
  const currentIndex = Math.min(
    clauses.findIndex((clause) => !clause.confirmed),
    clauses.length - 1
  );
  const safeIndex = currentIndex < 0 ? clauses.length - 1 : currentIndex;
  const current = clauses[safeIndex];
  const allConfirmed = completedCount === clauses.length;

  const importance = useMemo(() => {
    if (current.importanceLevel === 'critical') return { label: '必须确认', variant: 'danger' as const };
    return { label: '重要条款', variant: 'warning' as const };
  }, [current.importanceLevel]);

  const markListened = () => {
    setClauses((items) =>
      items.map((item) =>
        item.id === current.id
          ? { ...item, listened: true, deliveryStatus: 'delivered' }
          : item
      )
    );
  };

  const confirmCurrent = () => {
    setClauses((items) =>
      items.map((item) =>
        item.id === current.id
          ? {
              ...item,
              listened: true,
              confirmed: true,
              understandingStatus: 'understood',
              deliveryStatus: 'delivered',
            }
          : item
      )
    );
    setError('');
  };

  const needExplanation = async () => {
    const reason = `患者对知情同意条款“${current.clauseName}”表示不理解`;
    const nextClauses = clauses.map((item) =>
      item.id === current.id
        ? { ...item, understandingStatus: 'not_understood' as const }
        : item
    );
    const progress: ConsentProgress = {
      taskId,
      clauses: nextClauses,
      participantName: task?.participantName ?? task?.patientName ?? '患者',
      decision: 'needs_explanation',
      signatureData,
    };
    setSubmitting(true);
    try {
      const response = await careRepository.requestHandoff(taskId, reason);
      applyRealtimeEvent(
        toHandoffSseEnvelope(response, {
          taskId,
          sessionId: task?.sessionId,
          eventType: 'handoff_requested',
        })
      );
      await careRepository.submitConsent(progress);
      setClauses(nextClauses);
      saveConsent(progress);
      setError('已通知护士进行人工解释，当前进度已保存。');
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : '通知护士失败，请重试'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async () => {
    if (!allConfirmed) {
      setError('请先完成所有关键条款确认');
      return;
    }
    if (!signatureData) {
      setError('请完成演示手写签名');
      return;
    }
    const progress: ConsentProgress = {
      taskId,
      clauses,
      participantName: task?.participantName ?? task?.patientName ?? '患者',
      decision: 'agreed',
      signatureData,
      completedAt: new Date().toISOString(),
    };
    setSubmitting(true);
    try {
      await careRepository.submitConsent(progress);
      saveConsent(progress);
      updateTask(taskId, { taskStatus: 'pending_review' });
      router.push(`/patient/complete/${taskId}`);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : '知情同意提交失败，请重试'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PatientLayout title="知情同意确认" showBack>
      <div className="max-w-xl mx-auto p-4 space-y-4">
        <Card padding="lg">
          <div className="flex items-center justify-between mb-3">
            <div>
              <Badge variant="primary" size="sm">入院须知 v1.0</Badge>
              <h1 className="text-2xl mt-2">关键条款宣讲</h1>
            </div>
            <div className="flex flex-col items-end gap-2">
              <IntegrationStatus compact />
              <span className="text-sm text-foreground-muted">{completedCount}/{clauses.length}</span>
            </div>
          </div>
          <Progress value={completedCount} max={clauses.length} size="sm" />
          <p className="text-xs text-foreground-muted mt-3">
            “已听完”“已理解”“已同意”和“已签名”是不同状态。本页面仅用于原型演示。
          </p>
        </Card>

        {!allConfirmed && (
          <Card padding="lg">
            <div className="flex items-center justify-between mb-4">
              <Badge variant={importance.variant}>{importance.label}</Badge>
              <span className="text-xs text-foreground-muted">第 {safeIndex + 1} 条</span>
            </div>
            <h2 className="text-xl mb-3">{current.clauseName}</h2>
            <p className="text-base leading-8">{current.patientContent}</p>
            <button
              type="button"
              onClick={markListened}
              className="mt-5 w-full rounded-xl bg-surface-secondary border border-border p-4 flex items-center justify-center gap-2 text-primary"
            >
              <SpeakerWaveIcon className="w-5 h-5" />
              {current.listened ? '重新播放条款' : '播放条款（原型模拟）'}
            </button>
            <div className="grid grid-cols-2 gap-3 mt-4">
              <Button
                variant="outline"
                loading={submitting}
                onClick={() => void needExplanation()}
              >
                我不理解
              </Button>
              <Button onClick={confirmCurrent} disabled={!current.listened}>
                已理解并确认
              </Button>
            </div>
          </Card>
        )}

        {allConfirmed && (
          <Card padding="lg">
            <div className="flex items-center gap-2 text-green-700 mb-4">
              <CheckCircleIcon className="w-6 h-6" />
              <span className="font-medium">所有关键条款均已理解确认</span>
            </div>
            <h2 className="text-xl mb-3">参与人手写签名</h2>
            <SignaturePad onChange={setSignatureData} />
          </Card>
        )}

        {error && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex gap-2 text-sm text-amber-800">
            <ExclamationTriangleIcon className="w-5 h-5 flex-shrink-0" />
            {error}
          </div>
        )}

        {allConfirmed && (
          <Button
            className="w-full"
            size="lg"
            loading={submitting}
            onClick={() => void submit()}
          >
            确认同意并提交
          </Button>
        )}
      </div>
    </PatientLayout>
  );
}
