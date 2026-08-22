import type { SVGProps } from 'react';
import { cn } from '@/lib/utils';

export type PatientIconName =
  | 'brand-heart-cross'
  | 'nav-home'
  | 'nav-tasks'
  | 'nav-assistant'
  | 'nav-profile'
  | 'bell'
  | 'location'
  | 'phone'
  | 'clipboard'
  | 'chat'
  | 'sparkles'
  | 'document'
  | 'check-circle'
  | 'clock'
  | 'shield'
  | 'user'
  | 'family'
  | 'qr'
  | 'microphone'
  | 'keyboard'
  | 'stop'
  | 'interrupt'
  | 'send'
  | 'replay'
  | 'lock'
  | 'nurse'
  | 'warning'
  | 'play'
  | 'pause'
  | 'edit'
  | 'hospital'
  | 'menu';

interface PatientIconProps extends SVGProps<SVGSVGElement> {
  name: PatientIconName;
  label?: string;
}

export function PatientIcon({
  name,
  label,
  className,
  ...props
}: PatientIconProps) {
  return (
    <svg
      aria-hidden={label ? undefined : true}
      aria-label={label}
      className={cn('h-6 w-6 shrink-0', className)}
      focusable="false"
      viewBox="0 0 24 24"
      {...props}
    >
      <use href={`/assets/patient/icons/patient-icons.svg#${name}`} />
    </svg>
  );
}

export function PatientBrandMark({
  className,
}: {
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex h-12 w-12 items-center justify-center rounded-[18px] bg-gradient-to-br from-[#ff7659] to-[#ff4f31] text-white shadow-[0_10px_24px_rgba(255,86,52,.24)]',
        className
      )}
      aria-hidden="true"
    >
      <PatientIcon name="brand-heart-cross" className="h-7 w-7" />
    </span>
  );
}
