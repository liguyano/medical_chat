import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="max-w-md text-center rounded-3xl border border-border bg-surface p-8 shadow-sm">
        <div className="text-6xl font-serif text-primary">404</div>
        <h1 className="text-2xl mt-3">页面不存在</h1>
        <p className="text-sm text-foreground-muted mt-2">该原型页面尚未开放，或链接已经失效。</p>
        <Link
          href="/"
          className="inline-flex mt-5 rounded-full bg-primary px-5 py-2.5 text-white font-medium"
        >
          返回系统入口
        </Link>
      </div>
    </div>
  );
}
