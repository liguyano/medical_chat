'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import SignaturePad from '@/components/consent/SignaturePad';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { createClientInvocationId } from '@/lib/clientInvocation';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { applyRealtimeEvent } from '@/lib/transports/applyRealtimeEvent';
import { toHandoffSseEnvelope } from '@/lib/transports/handoffResponse';
import type { ConsentClause, ConsentProgress } from '@/lib/types';

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
  const initialClauseState =
    runtimeConfig.dataMode === 'api'
      ? []
      : (savedConsent?.clauses ?? initialClauses);
  const [clauses, setClauses] = useState(initialClauseState);
  const [activeClauseIndex, setActiveClauseIndex] = useState(() => {
    const source = initialClauseState;
    const firstUnconfirmed = source.findIndex((clause) => !clause.confirmed);
    return firstUnconfirmed < 0 ? source.length - 1 : firstUnconfirmed;
  });
  const [signatureData, setSignatureData] = useState(savedConsent?.signatureData);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [remoteRecordId, setRemoteRecordId] = useState<number>();
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const handoffSubmittingRef = useRef(false);

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api') return;
    let cancelled = false;
    void careRepository
      .getConsentSnapshot(taskId)
      .then((snapshot) => {
        if (cancelled) return;
        setRemoteRecordId(snapshot.recordId);
        const remoteClauses: ConsentClause[] = snapshot.clauses.map((raw, index) => {
          const id = String(raw.id ?? raw.clause_id ?? `consent-${index + 1}`);
          const confirmation = snapshot.confirmations.find(
            (item) => String(item.clause_id ?? '') === id
          );
          const result = String(confirmation?.confirmation_result ?? '');
          return {
            id,
            clauseCode: String(raw.clause_code ?? id),
            clauseName: String(raw.title ?? raw.clause_title ?? '知情同意条款'),
            patientContent: String(raw.patient_content ?? raw.original_content ?? ''),
            audioUrl:
              typeof raw.audio_url === 'string' ? raw.audio_url : undefined,
            audioDurationSeconds:
              typeof raw.audio_duration_seconds === 'number'
                ? raw.audio_duration_seconds
                : undefined,
            importanceLevel:
              raw.importance_level === 'critical' ? 'critical' : 'important',
            mandatoryDelivery: Boolean(raw.confirmation_required ?? true),
            explicitConfirmationRequired: Boolean(raw.confirmation_required ?? true),
            deliveryStatus: confirmation ? 'delivered' : 'pending',
            listened: snapshot.playback.some(
              (item) =>
                String(item.clause_id ?? '') === id &&
                item.playback_status === 'completed'
            ),
            confirmed: result === '已理解并确认',
            understandingStatus:
              result === '已理解并确认'
                ? 'understood'
                : result
                  ? 'not_understood'
                  : undefined,
          };
        });
        setClauses(remoteClauses);
        const firstUnconfirmed = remoteClauses.findIndex(
          (clause) => !clause.confirmed
        );
        setActiveClauseIndex(
          firstUnconfirmed < 0 ? remoteClauses.length - 1 : firstUnconfirmed
        );
      })
      .catch((loadError) => {
        if (!cancelled) {
          setClauses([]);
          setError(loadError instanceof Error ? loadError.message : '知情同意内容加载失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  const completedCount = clauses.filter((clause) => clause.confirmed).length;
  const safeIndex = Math.min(
    Math.max(activeClauseIndex, 0),
    clauses.length - 1
  );
  const current = clauses[safeIndex];
  const allConfirmed = completedCount === clauses.length;

  const importance = useMemo(() => {
    if (!current) return '内容暂不可用';
    if (current.importanceLevel === 'critical') return '必须确认';
    return '重要条款';
  }, [current]);

  const markListened = () => {
    if (!current) return;
    setClauses((items) =>
      items.map((item) =>
        item.id === current.id
          ? { ...item, listened: true, deliveryStatus: 'delivered' }
          : item
      )
    );
    if (runtimeConfig.dataMode === 'api' && remoteRecordId) {
      const clauseId = Number(current.id);
      if (Number.isSafeInteger(clauseId)) {
        void careRepository.recordConsentPlayback(taskId, {
          clauseId,
          eventType: 'complete',
          positionSeconds: 0,
          clientInvocationId: createClientInvocationId('consent-playback'),
        });
      }
    }
  };

  const handlePlayback = async () => {
    if (!current) return;
    if (current.audioUrl && runtimeConfig.dataMode === 'api') {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      const audio = new Audio(current.audioUrl);
      audioRef.current = audio;
      setPlaying(true);
      const clauseId = Number(current.id);
      if (remoteRecordId && Number.isSafeInteger(clauseId)) {
        void careRepository.recordConsentPlayback(taskId, {
          clauseId,
          eventType: current.listened ? 'replay' : 'start',
          positionSeconds: 0,
          clientInvocationId: createClientInvocationId('consent-playback'),
        });
      }
      audio.addEventListener('ended', () => {
        setPlaying(false);
        audioRef.current = null;
        markListened();
      });
      audio.addEventListener('error', () => {
        setPlaying(false);
        audioRef.current = null;
        setError('条款音频暂时无法播放，请稍后重试或联系护士');
      });
      try {
        await audio.play();
      } catch {
        setPlaying(false);
        audioRef.current = null;
        setError('浏览器未能播放条款音频，请点击重试');
      }
      return;
    }
    markListened();
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds || seconds <= 0) return '—';
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
  };

  if (!current) {
    return (
      <PatientLayout title="知情同意确认" showBack>
        <div className="px-[18px] py-8">
          <div
            role="alert"
            className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800"
          >
            <PatientIcon name="warning" className="mr-2 inline h-5 w-5" />
            {error || '知情同意内容暂不可用，请联系护士处理。'}
          </div>
        </div>
      </PatientLayout>
    );
  }

  const confirmCurrent = async () => {
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
    if (runtimeConfig.dataMode === 'api') {
      const clauseId = Number(current.id);
      if (Number.isSafeInteger(clauseId)) {
        await careRepository.confirmConsentClause(taskId, clauseId, {
          confirmationResult: '已理解并确认',
        });
      }
    }
    setActiveClauseIndex((index) => Math.min(index + 1, clauses.length - 1));
    setError('');
  };

  const needExplanation = async () => {
    if (handoffSubmittingRef.current) return;
    handoffSubmittingRef.current = true;
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
      const response = await careRepository.requestHandoff(taskId, reason, {
        requestedAction: 'explain_consent',
        clientInvocationId: createClientInvocationId('patient-handoff'),
      });
      if (runtimeConfig.dataMode === 'api') {
        const clauseId = Number(current.id);
        if (Number.isSafeInteger(clauseId)) {
          await careRepository.confirmConsentClause(taskId, clauseId, {
            confirmationResult: '未理解',
            patientReply: reason,
          });
        }
      }
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
      handoffSubmittingRef.current = false;
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
    <PatientLayout
      title="知情同意确认"
      showBack
      headerRight={
        <span className="rounded-full bg-[#fff0e8] px-3 py-1 text-sm font-black text-primary">
          2/3
        </span>
      }
    >
      <div className="space-y-4 px-[18px] pb-8 pt-4">
        <section className="px-2 py-1">
          <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-start">
            {[
              { label: '1 评估', done: true },
              { label: '2 知情同意', done: allConfirmed },
              { label: '3 完成', done: false },
            ].map((step, index) => (
              <div key={step.label} className="contents">
                <div className="flex flex-col items-center">
                  <span
                    className={`grid h-9 w-9 place-items-center rounded-full text-sm font-black ${
                      index < 2
                        ? 'bg-primary text-white'
                        : 'bg-[#eae5df] text-foreground-muted'
                    }`}
                  >
                    {step.done ? (
                      <PatientIcon name="check-circle" className="h-5 w-5" />
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span
                    className={`mt-2 text-xs font-bold ${
                      index < 2 ? 'text-primary' : 'text-foreground-muted'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {index < 2 && (
                  <span
                    className={`mt-[18px] h-0.5 min-w-8 ${
                      index === 0
                        ? 'bg-primary'
                        : 'border-t-2 border-[#ddd4cc]'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </section>

        {!allConfirmed && (
          <section className="patient-card-soft p-4">
            <div className="flex items-center gap-3">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-[#ff7658] to-[#ff4f31] text-white">
                <PatientIcon name="shield" className="h-7 w-7" />
              </span>
              <h1 className="min-w-0 flex-1 text-[22px] font-black">
                {current.clauseName}
              </h1>
              <span className="rounded-full bg-[#ffe7e1] px-3 py-1 text-sm font-black text-danger">
                {importance}
              </span>
            </div>

            <p className="mt-5 text-[17px] font-medium leading-8">
              {current.patientContent}
            </p>

            <button
              type="button"
              onClick={() => void handlePlayback()}
              className="mt-5 flex min-h-[76px] w-full items-center gap-3 rounded-[18px] border border-[#f0c8a7] bg-white/75 px-4 text-left"
            >
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-primary text-white">
                <PatientIcon
                  name={current.listened ? 'replay' : 'play'}
                  className="h-6 w-6"
                />
              </span>
              <span className="font-black">
                {playing
                  ? '正在播放条款'
                  : current.listened
                    ? '重新播放条款'
                    : '播放条款'}
              </span>
              <span className="flex h-8 flex-1 items-center justify-center gap-[3px] overflow-hidden text-primary">
                {[10, 18, 12, 24, 15, 22, 12, 17, 25, 14, 20, 11].map(
                  (height, index) => (
                    <span
                      key={`${height}-${index}`}
                      className="w-[3px] rounded-full bg-current"
                      style={{ height }}
                    />
                  )
                )}
              </span>
              <span className="text-xs text-foreground-muted">
                {formatDuration(current.audioDurationSeconds) === '—'
                  ? '01:02'
                  : formatDuration(current.audioDurationSeconds)}
              </span>
            </button>
          </section>
        )}

        <section className="flex items-center justify-between px-3">
          <button
            type="button"
            onClick={() =>
              setActiveClauseIndex((index) => Math.max(index - 1, 0))
            }
            className="patient-touch-button border border-[#efc7a9] bg-white text-primary disabled:opacity-40"
            disabled={safeIndex === 0}
            aria-label="上一条条款"
          >
            <span aria-hidden="true" className="text-2xl leading-none">‹</span>
          </button>
          <p className="text-[15px] font-bold">
            {safeIndex + 1} / {clauses.length} 条款
          </p>
          <button
            type="button"
            onClick={() =>
              setActiveClauseIndex((index) =>
                Math.min(index + 1, clauses.length - 1)
              )
            }
            className="patient-touch-button bg-primary text-white disabled:opacity-40"
            disabled={allConfirmed || safeIndex === clauses.length - 1}
            aria-label="下一条条款"
          >
            <span aria-hidden="true" className="text-2xl leading-none">›</span>
          </button>
        </section>

        {!allConfirmed && (
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              disabled={submitting}
              className="patient-outline-button px-2 text-[14px] disabled:opacity-50"
                onClick={() => void needExplanation()}
            >
              <PatientIcon name="nurse" className="h-5 w-5" />
              {submitting ? '正在通知' : '我不理解，请找护士'}
            </button>
            <button
              type="button"
              onClick={() => void confirmCurrent()}
              disabled={!current.listened}
              className="patient-primary-button px-2 text-[14px]"
            >
              <PatientIcon name="check-circle" className="h-5 w-5" />
              已理解并确认
            </button>
          </div>
        )}

        <section className="border-t border-dashed border-[#ded5cd] pt-4">
          {allConfirmed && (
            <div className="mb-3 flex items-center gap-2 rounded-2xl bg-[#eaf7f2] p-3 text-sm font-bold text-[#268163]">
              <PatientIcon name="check-circle" className="h-5 w-5" />
              所有关键条款均已理解确认
            </div>
          )}
          <h2 className="mb-3 text-[17px] font-black">完成签名后提交</h2>
          <SignaturePad
            onChange={setSignatureData}
            disabled={!allConfirmed}
          />
        </section>

        {error && (
          <div
            role="alert"
            className="flex gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800"
          >
            <PatientIcon name="warning" className="h-5 w-5 shrink-0" />
            {error}
          </div>
        )}

        {allConfirmed && (
          <button
            className="patient-primary-button w-full"
            disabled={submitting || !signatureData}
            onClick={() => void submit()}
          >
            {submitting ? '正在提交…' : '确认同意并提交'}
          </button>
        )}
      </div>
    </PatientLayout>
  );
}
