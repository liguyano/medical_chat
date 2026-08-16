'use client';

import { ReactNode } from 'react';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  BellIcon,
  ChatBubbleLeftRightIcon,
  HomeIcon,
} from '@heroicons/react/24/outline';
import { usePathname, useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';

interface PatientLayoutProps {
  children: ReactNode;
  title?: string;
  showBack?: boolean;
  onBack?: () => void;
  showNavigation?: boolean;
}

export default function PatientLayout({
  children,
  title,
  showBack = false,
  onBack,
  showNavigation = false,
}: PatientLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      router.back();
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* 顶部标题栏（移动端优化） */}
      {(showBack || title) && (
        <header className="sticky top-0 z-50 bg-surface/90 backdrop-blur-md border-b border-border">
          <div className="flex items-center h-14 px-4">
            {showBack && (
              <button
                onClick={handleBack}
                className="mr-3 p-2 -ml-2 rounded-full hover:bg-surface-secondary transition-colors"
                aria-label="返回"
              >
                <ArrowLeftIcon className="w-5 h-5 text-foreground" />
              </button>
            )}
            {title && (
              <h1 className="text-lg font-medium text-foreground flex-1 text-center pr-10">
                {title}
              </h1>
            )}
          </div>
        </header>
      )}

      {/* 主内容区 */}
      <main className={showNavigation ? 'pb-24' : 'pb-safe'}>{children}</main>

      {showNavigation && (
        <nav className="fixed bottom-0 inset-x-0 z-50 border-t border-border bg-surface/95 backdrop-blur-md">
          <div className="max-w-xl mx-auto grid grid-cols-3 px-3 py-2 safe-area-pb">
            {[
              { href: '/patient/home', label: '首页', icon: HomeIcon },
              { href: '/patient/tasks', label: '任务', icon: BellIcon },
              { href: '/patient/assistant', label: '住院助手', icon: ChatBubbleLeftRightIcon },
            ].map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    'flex flex-col items-center gap-1 rounded-xl py-2 text-xs',
                    active ? 'text-primary bg-primary-tint' : 'text-foreground-muted'
                  )}
                >
                  <item.icon className="w-5 h-5" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </nav>
      )}
    </div>
  );
}
