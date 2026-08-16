'use client';

import { ReactNode } from 'react';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { useRouter } from 'next/navigation';

interface PatientLayoutProps {
  children: ReactNode;
  title?: string;
  showBack?: boolean;
  onBack?: () => void;
}

export default function PatientLayout({
  children,
  title,
  showBack = false,
  onBack,
}: PatientLayoutProps) {
  const router = useRouter();

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
      <main className="pb-safe">{children}</main>
    </div>
  );
}
