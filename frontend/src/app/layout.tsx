import type { Metadata } from 'next';
import { NetworkStatus } from '@/components/shared/NetworkStatus';
import './globals.css';

export const metadata: Metadata = {
  title: '智能护理评估原型',
  description: '住院患者入院评估、宣教、知情同意与护士复核交互原型',
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <NetworkStatus />
        {children}
      </body>
    </html>
  );
}
