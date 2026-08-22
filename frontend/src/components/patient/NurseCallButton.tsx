'use client';

import { useRef, useState } from 'react';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { careRepository } from '@/lib/repositories';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { cn } from '@/lib/utils';

export function NurseCallButton({
  taskId,
  reason = '患者在住院服务页面主动呼叫护士',
  className,
  compact = false,
  iconOnly = false,
}: {
  taskId?: string;
  reason?: string;
  className?: string;
  compact?: boolean;
  iconOnly?: boolean;
}) {
  const updateTask = useTaskStore((state) => state.updateTask);
  const invocationIdRef = useRef<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'sent' | 'error'>(
    'idle'
  );

  const requestNurse = async () => {
    if (!taskId || status === 'loading') return;
    const clientInvocationId = crypto.randomUUID();
    invocationIdRef.current = clientInvocationId;
    setStatus('loading');
    try {
      await careRepository.requestHandoff(taskId, reason, {
        requestedAction: 'patient_home_call',
        urgency: 'routine',
        clientInvocationId,
      });
      if (invocationIdRef.current !== clientInvocationId) return;
      updateTask(taskId, {
        handoffRequired: true,
        handoffReason: reason,
      });
      setStatus('sent');
    } catch {
      if (invocationIdRef.current === clientInvocationId) {
        setStatus('error');
      }
    }
  };

  const label =
    status === 'loading'
      ? '正在呼叫'
      : status === 'sent'
        ? '护士已收到'
        : status === 'error'
          ? '重试呼叫'
          : compact
            ? '找护士'
            : '随时呼叫护士';

  return (
    <button
      type="button"
      onClick={() => void requestNurse()}
      disabled={!taskId || status === 'loading' || status === 'sent'}
      className={cn(
        compact
          ? 'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full bg-gradient-to-r from-[#ff6848] to-[#ff5133] px-4 text-sm font-bold text-white'
          : 'patient-primary-button',
        className
      )}
      aria-live="polite"
      aria-label={iconOnly ? label : undefined}
    >
      <PatientIcon name="nurse" className={compact ? 'h-5 w-5' : 'h-6 w-6'} />
      {iconOnly ? <span className="sr-only">{label}</span> : label}
    </button>
  );
}
