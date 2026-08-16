'use client';

import { useSyncExternalStore } from 'react';
import { SignalSlashIcon } from '@heroicons/react/24/outline';

function subscribe(callback: () => void) {
  window.addEventListener('online', callback);
  window.addEventListener('offline', callback);
  return () => {
    window.removeEventListener('online', callback);
    window.removeEventListener('offline', callback);
  };
}

export function NetworkStatus() {
  const online = useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true
  );

  if (online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 top-0 z-[100] flex items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-center text-sm text-amber-900 shadow-sm"
    >
      <SignalSlashIcon className="h-4 w-4 flex-shrink-0" />
      网络连接已中断，当前内容已保存在本机；恢复连接后可继续操作。
    </div>
  );
}
