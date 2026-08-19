'use client';

import { ReactNode, useEffect, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useUserStore } from '@/lib/stores/useUserStore';
import { careRepository } from '@/lib/repositories';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { runtimeConfig } from '@/lib/runtime/config';
import { useRealtimeStream } from '@/hooks/useRealtimeStream';
import { useChatStore } from '@/lib/stores/useChatStore';
import { createNurseAlertsSsePath } from '@/lib/transports/sseClient';
import {
  HomeIcon,
  ClipboardDocumentListIcon,
  UserGroupIcon,
  ComputerDesktopIcon,
  StarIcon,
  Cog6ToothIcon,
  UserCircleIcon,
  BellAlertIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

interface NurseLayoutProps {
  children: ReactNode;
}

const navigation = [
  { name: '工作台', href: '/nurse/dashboard', icon: HomeIcon },
  { name: '患者管理', href: '/nurse/patients', icon: UserGroupIcon },
  { name: '任务管理', href: '/nurse/tasks', icon: ClipboardDocumentListIcon },
  { name: '实时监控', href: '/nurse/monitor', icon: ComputerDesktopIcon },
  { name: 'AI质评', href: '/nurse/quality', icon: StarIcon },
  { name: '系统配置', href: '/nurse/config', icon: Cog6ToothIcon },
];

const subscribeToHydration = () => () => undefined;

export default function NurseLayout({ children }: NurseLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, login, logout, isAuthenticated } = useUserStore();
  const [sessionChecked, setSessionChecked] = useState(
    runtimeConfig.dataMode !== 'api'
  );
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false
  );
  const nurseRequests = useChatStore(
    (state) => state.nurseAssistanceRequests
  );
  const [dismissedRequests, setDismissedRequests] = useState<string[]>([]);
  const activeRequests = Object.values(nurseRequests)
    .filter(
      (request) =>
        request.status === 'requested' &&
        !dismissedRequests.includes(request.requestId)
    )
    .sort((left, right) =>
      right.occurredAt.localeCompare(left.occurredAt)
    );
  const { status: nurseAlertStatus } = useRealtimeStream({
    path: createNurseAlertsSsePath(),
    enabled: hydrated && sessionChecked && isAuthenticated,
  });

  useEffect(() => {
    if (!hydrated || runtimeConfig.dataMode !== 'api') return;
    const controller = new AbortController();
    void careRepository
      .getCurrentStaff(controller.signal)
      .then((currentUser) => login(currentUser))
      .catch((error) => {
        if (!isRequestCancelled(error)) logout();
      })
      .finally(() => {
        if (!controller.signal.aborted) setSessionChecked(true);
      });
    return () => abortRequest(controller);
  }, [hydrated, login, logout]);

  useEffect(() => {
    if (hydrated && sessionChecked && !isAuthenticated) {
      router.replace('/nurse/login');
    }
  }, [hydrated, isAuthenticated, router, sessionChecked]);

  const handleLogout = () => {
    void careRepository.logoutStaff().catch(() => undefined);
    logout();
    router.push('/nurse/login');
  };

  if (!hydrated || !sessionChecked || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-sm text-foreground-muted">正在验证医护身份...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* 顶部导航栏 */}
      <nav className="sticky top-0 z-50 bg-surface/80 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center space-x-8">
              <Link href="/nurse/dashboard" className="flex items-center space-x-2">
                <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                  <span className="text-white font-bold">医</span>
                </div>
                <span className="text-xl font-serif font-medium">智能护理评估</span>
              </Link>

              {/* 导航菜单 */}
              <div className="hidden xl:flex space-x-1">
                {navigation.map((item) => {
                  const isActive = pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      className={cn(
                        'flex items-center space-x-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200',
                        isActive
                          ? 'bg-primary-tint text-primary'
                          : 'text-foreground-muted hover:bg-surface-secondary hover:text-foreground'
                      )}
                    >
                      <item.icon className="w-5 h-5" />
                      <span>{item.name}</span>
                    </Link>
                  );
                })}
              </div>
            </div>

            {/* 用户信息 */}
            <div className="flex items-center space-x-4">
              <div className="hidden sm:block text-right">
                <div className="text-sm font-medium text-foreground">{user?.name}</div>
                <div className="text-xs text-foreground-muted">{user?.department}</div>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 rounded-full hover:bg-surface-secondary transition-colors"
                title="退出登录"
              >
                <UserCircleIcon className="w-8 h-8 text-foreground-muted" />
              </button>
            </div>
          </div>
        </div>
      </nav>

      <div className="xl:hidden overflow-x-auto border-b border-border bg-surface">
        <div className="flex min-w-max px-3 py-2 gap-1">
          {navigation.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-2 rounded-full text-sm whitespace-nowrap',
                  isActive
                    ? 'bg-primary-tint text-primary'
                    : 'text-foreground-muted hover:bg-surface-secondary'
                )}
              >
                <item.icon className="w-4 h-4" />
                {item.name}
              </Link>
            );
          })}
        </div>
      </div>

      {/* 主内容区 */}
      {activeRequests.length > 0 && (
        <aside
          className="fixed right-4 top-20 z-[60] w-[min(24rem,calc(100vw-2rem))] space-y-3"
          aria-label="患者呼叫提醒"
        >
          {activeRequests.slice(0, 3).map((request) => (
            <div
              key={request.requestId}
              className="rounded-2xl border border-red-200 bg-white p-4 shadow-xl"
            >
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-red-100 p-2 text-red-700">
                  <BellAlertIcon className="h-6 w-6" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-red-800">患者呼叫护士</p>
                    {request.urgency === 'urgent' && (
                      <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs text-white">
                        紧急
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm font-medium">
                    {request.patientName || `任务 ${request.taskId}`}
                    {request.bedNo ? ` · ${request.bedNo}` : ''}
                  </p>
                  <p className="mt-1 text-sm text-foreground-muted">
                    {request.actionLabel}：{request.reason}
                  </p>
                  <div className="mt-3 flex items-center gap-3">
                    <Link
                      href={`/nurse/monitor/${request.taskId}`}
                      className="text-sm font-medium text-primary"
                    >
                      立即查看
                    </Link>
                    <span className="text-xs text-foreground-muted">
                      提醒流 {nurseAlertStatus === 'connected' ? '已连接' : '连接中'}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setDismissedRequests((current) => [
                      ...current,
                      request.requestId,
                    ])
                  }
                  className="text-foreground-muted"
                  aria-label="暂时关闭提醒"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>
            </div>
          ))}
        </aside>
      )}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
    </div>
  );
}
