'use client';

import { Button } from '@/components/shared/Button';

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="max-w-md text-center rounded-3xl border border-red-200 bg-surface p-8 shadow-sm">
        <h1 className="text-2xl">页面暂时无法显示</h1>
        <p className="text-sm text-foreground-muted mt-2">
          已保存的数据不会因此丢失，请尝试重新加载页面。
        </p>
        <Button className="mt-5" onClick={reset}>重新加载</Button>
      </div>
    </div>
  );
}
