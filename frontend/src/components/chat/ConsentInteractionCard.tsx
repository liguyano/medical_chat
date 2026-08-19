'use client';

import { useEffect, useRef, useState } from 'react';
import SignaturePad from '@/components/consent/SignaturePad';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import type {
  ConsentClause,
  ConsentProgress,
  ConsentRequest,
} from '@/lib/types';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  SpeakerWaveIcon,
} from '@heroicons/react/24/outline';

interface ConsentInteractionCardProps {
  request: ConsentRequest;
  participantName: string;
  onSubmit: (progress: ConsentProgress) => Promise<void>;
  readOnly?: boolean;
}

function statusLabel(request: ConsentRequest): string {
  if (request.status === 'signed') return '患者已确认并签署';
  if (request.status === 'refused') return '患者已拒绝';
  if (request.status === 'needs_explanation') return '患者请求护士解释';
  return '待患者确认';
}

export default function ConsentInteractionCard({
  request,
  participantName,
  onSubmit,
  readOnly = false,
}: ConsentInteractionCardProps) {
  const autoPlayedRef = useRef(false);
  const [clauses, setClauses] = useState(request.clauses);
  const [signatureData, setSignatureData] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const speak = (text: string) => {
    if (
      typeof window === 'undefined' ||
      !('speechSynthesis' in window) ||
      !text
    ) {
      setError('当前浏览器不支持自动播报，请直接阅读条款原文。');
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  };

  useEffect(() => {
    if (readOnly || !request.autoPlay || autoPlayedRef.current) return;
    autoPlayedRef.current = true;
    speak(request.fullText);
    return () => {
      if (
        typeof window !== 'undefined' &&
        'speechSynthesis' in window
      ) {
        window.speechSynthesis.cancel();
      }
    };
    // 同一表单仅自动播报一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, request.formId]);

  const updateClause = (
    clauseId: string,
    updates: Partial<ConsentClause>
  ) => {
    setClauses((current) =>
      current.map((clause) =>
        clause.id === clauseId ? { ...clause, ...updates } : clause
      )
    );
  };

  const mandatoryConfirmed = clauses
    .filter(
      (clause) =>
        clause.mandatoryDelivery || clause.explicitConfirmationRequired
    )
    .every((clause) => clause.listened && clause.confirmed);

  const submit = async (
    decision: ConsentProgress['decision']
  ) => {
    if (decision === 'agreed' && !mandatoryConfirmed) {
      setError('请先逐条阅读并确认所有必须条款。');
      return;
    }
    if (decision === 'agreed' && request.requiresSignature && !signatureData) {
      setError('请完成手写签名。');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onSubmit({
        taskId: request.taskId,
        formId: request.formId,
        documentVersion: request.documentVersion,
        clauses,
        participantName,
        decision,
        signatureData,
        completedAt:
          decision === 'agreed' ? new Date().toISOString() : undefined,
      });
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

  if (readOnly || request.status !== 'pending_signature') {
    return (
      <section
        className={`mb-4 overflow-hidden rounded-2xl border p-4 ${
          request.status === 'signed'
            ? 'border-green-200 bg-green-50'
            : 'border-amber-200 bg-amber-50'
        }`}
        aria-label={`知情同意历史：${request.title}`}
      >
        <div className="flex flex-wrap items-center gap-2">
          {request.status === 'signed' ? (
            <CheckCircleIcon className="h-5 w-5 text-green-700" />
          ) : (
            <ExclamationTriangleIcon className="h-5 w-5 text-amber-700" />
          )}
          <span className="font-medium">{request.title}</span>
          <Badge
            variant={request.status === 'signed' ? 'success' : 'warning'}
            size="sm"
          >
            {statusLabel(request)}
          </Badge>
        </div>
        <p
          className={`mt-1 text-xs ${
            request.status === 'signed' ? 'text-green-700' : 'text-amber-700'
          }`}
        >
          文档版本 {request.documentVersion}
        </p>
        {request.fullText && (
          <div className="mt-3 rounded-xl border border-violet-100 bg-white p-4">
            <p className="mb-2 text-xs font-medium text-violet-800">
              知情同意全文
            </p>
            <p className="whitespace-pre-wrap text-sm leading-7">
              {request.fullText}
            </p>
          </div>
        )}
        <div className="mt-3 space-y-3">
          {request.clauses.map((clause, index) => (
            <article
              key={clause.id}
              className="rounded-xl border border-violet-100 bg-white p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs text-foreground-muted">
                    第 {index + 1} 条
                  </p>
                  <h3 className="mt-1 text-sm font-semibold">
                    {clause.clauseName}
                  </h3>
                </div>
                {clause.importanceLevel === 'critical' && (
                  <Badge variant="danger" size="sm">
                    必须确认
                  </Badge>
                )}
              </div>
              <p className="mt-3 text-sm leading-7">
                {clause.patientContent}
              </p>
              <p className="mt-3 text-xs text-foreground-muted">
                患者操作：
                {clause.confirmed
                  ? '已阅读并确认'
                  : clause.listened
                    ? '已播放/阅读，未确认'
                    : '未完成阅读'}
              </p>
            </article>
          ))}
        </div>
        {request.completedAt && (
          <p className="mt-3 text-xs text-foreground-muted">
            操作时间：{new Date(request.completedAt).toLocaleString('zh-CN')}
          </p>
        )}
      </section>
    );
  }

  return (
    <section
      className="mb-4 overflow-hidden rounded-2xl border border-violet-200 bg-violet-50"
      aria-label={`知情同意：${request.title}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-violet-200 px-4 py-3">
        <div>
          <Badge variant="primary" size="sm">
            知情同意
          </Badge>
          <h2 className="mt-2 font-semibold">{request.title}</h2>
          <p className="mt-1 text-xs text-foreground-muted">
            文档版本 {request.documentVersion}
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => speak(request.fullText)}
        >
          <SpeakerWaveIcon className="mr-1 h-4 w-4" />
          播放全文
        </Button>
      </div>

      <div className="space-y-3 p-4">
        {clauses.map((clause, index) => (
          <article
            key={clause.id}
            className="rounded-xl border border-violet-100 bg-white p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs text-foreground-muted">
                  第 {index + 1} 条
                </p>
                <h3 className="mt-1 text-sm font-semibold">
                  {clause.clauseName}
                </h3>
              </div>
              {clause.importanceLevel === 'critical' && (
                <Badge variant="danger" size="sm">
                  必须确认
                </Badge>
              )}
            </div>
            <p className="mt-3 text-sm leading-7">
              {clause.patientContent}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  speak(clause.patientContent);
                  updateClause(clause.id, {
                    listened: true,
                    deliveryStatus: 'delivered',
                  });
                }}
              >
                <SpeakerWaveIcon className="mr-1 h-4 w-4" />
                {clause.listened ? '重新播放' : '播放条款'}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={!clause.listened || clause.confirmed}
                onClick={() =>
                  updateClause(clause.id, {
                    listened: true,
                    confirmed: true,
                    deliveryStatus: 'delivered',
                    understandingStatus: 'understood',
                  })
                }
              >
                {clause.confirmed ? '已确认' : '已理解并确认'}
              </Button>
            </div>
          </article>
        ))}

        {mandatoryConfirmed && request.requiresSignature && (
          <div className="rounded-xl border border-violet-100 bg-white p-4">
            <h3 className="mb-3 text-sm font-semibold">
              {participantName}手写签名
            </h3>
            <SignaturePad onChange={setSignatureData} />
          </div>
        )}

        {error && (
          <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0" />
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Button
            type="button"
            variant="outline"
            loading={submitting}
            onClick={() => void submit('needs_explanation')}
          >
            我需要护士解释
          </Button>
          <Button
            type="button"
            loading={submitting}
            disabled={!mandatoryConfirmed}
            onClick={() => void submit('agreed')}
          >
            确认同意并提交
          </Button>
        </div>
      </div>
    </section>
  );
}
