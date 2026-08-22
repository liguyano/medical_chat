import Image from 'next/image';
import { cn } from '@/lib/utils';

type PatientStateKind =
  | 'loading'
  | 'empty-tasks'
  | 'voice-error'
  | 'paused'
  | 'complete'
  | 'readonly';

export function PatientState({
  kind,
  title,
  description,
  className,
}: {
  kind: PatientStateKind;
  title: string;
  description?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'patient-card flex flex-col items-center px-6 py-10 text-center',
        className
      )}
      role="status"
    >
      <Image
        src={`/assets/patient/states/${kind}.svg`}
        alt=""
        width={96}
        height={96}
        className="h-24 w-24"
      />
      <h2 className="mt-4 text-xl font-extrabold">{title}</h2>
      {description && (
        <p className="mt-2 text-[15px] leading-7 text-foreground-muted">
          {description}
        </p>
      )}
    </div>
  );
}
