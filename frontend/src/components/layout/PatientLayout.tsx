'use client';

import { ReactNode, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { usePathname, useRouter } from 'next/navigation';
import {
  PatientIcon,
  type PatientIconName,
} from '@/components/patient/PatientIcon';
import { cn } from '@/lib/utils';

interface PatientLayoutProps {
  children: ReactNode;
  title?: string;
  showBack?: boolean;
  onBack?: () => void;
  showNavigation?: boolean;
  headerRight?: ReactNode;
  contentClassName?: string;
}

export default function PatientLayout({
  children,
  title,
  showBack = false,
  onBack,
  showNavigation = false,
  headerRight,
  contentClassName,
}: PatientLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    document.documentElement.classList.add('patient-scrollbar');
    return () => document.documentElement.classList.remove('patient-scrollbar');
  }, []);

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      router.back();
    }
  };

  return (
    <div className="patient-app scrollbar-soft">
      <div className="patient-mobile-frame">
        {(showBack || title || headerRight) && (
          <header className="patient-topbar">
            <div className="flex items-center justify-start">
              {showBack && (
                <button
                  onClick={handleBack}
                  className="patient-touch-button text-foreground hover:bg-surface"
                  aria-label="返回"
                >
                  <ArrowLeftIcon className="h-6 w-6" />
                </button>
              )}
            </div>
            {title ? (
              <h1 className="patient-topbar-title">{title}</h1>
            ) : (
              <span />
            )}
            <div className="flex items-center justify-end">
              {headerRight}
            </div>
          </header>
        )}

        <main
          className={cn(
            'patient-page-content',
            showNavigation ? 'pb-[calc(92px+env(safe-area-inset-bottom))]' : 'pb-safe',
            contentClassName
          )}
        >
          {children}
        </main>

        {showNavigation && (
          <nav className="patient-bottom-nav" aria-label="患者端主导航">
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  { href: '/patient/home', label: '首页', icon: 'nav-home' },
                  { href: '/patient/tasks', label: '任务', icon: 'nav-tasks' },
                  {
                    href: '/patient/assistant',
                    label: '住院助手',
                    icon: 'nav-assistant',
                  },
                ] as Array<{
                  href: string;
                  label: string;
                  icon: PatientIconName;
                }>
              ).map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="patient-nav-item"
                    data-active={active}
                    aria-current={active ? 'page' : undefined}
                  >
                    <PatientIcon name={item.icon} className="h-[23px] w-[23px]" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </nav>
        )}
      </div>
    </div>
  );
}
