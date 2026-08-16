export default function Loading() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center">
        <div className="w-10 h-10 rounded-full border-4 border-primary-tint border-t-primary animate-spin mx-auto" />
        <p className="text-sm text-foreground-muted mt-3">正在加载护理评估原型...</p>
      </div>
    </div>
  );
}
