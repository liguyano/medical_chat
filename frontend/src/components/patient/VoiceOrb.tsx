import { PatientIcon } from '@/components/patient/PatientIcon';
import {
  getVoicePresentation,
  type VoicePresentationState,
} from '@/lib/patient/voicePresentation';
import { cn } from '@/lib/utils';

export function VoiceOrb({
  state,
  className,
}: {
  state: VoicePresentationState;
  className?: string;
}) {
  const copy = getVoicePresentation(state);
  const faceIcon =
    state === 'connecting'
      ? 'interrupt'
      : state === 'error' || state === 'text_fallback'
        ? 'warning'
        : state === 'paused' || state === 'closed'
          ? 'pause'
          : undefined;

  return (
    <div className={cn('flex flex-col items-center text-center', className)}>
      <div className="patient-orb" data-state={state} aria-label={copy.title}>
        <span className="patient-orb-wave" aria-hidden="true" />
        <span className="patient-orb-face" data-state={state}>
          {faceIcon ? (
            <PatientIcon name={faceIcon} className="h-8 w-8" />
          ) : (
            <span className="patient-orb-smile" aria-hidden="true" />
          )}
        </span>
      </div>
      <p
        className="mt-5 text-[25px] font-extrabold"
        style={{ color: copy.color }}
      >
        {copy.title}
      </p>
      <p className="mt-1 text-sm text-foreground-muted">{copy.detail}</p>
    </div>
  );
}
