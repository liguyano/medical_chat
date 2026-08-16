'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/shared/Button';
import { Input } from '@/components/shared/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/shared/Card';
import { useUserStore } from '@/lib/stores/useUserStore';
import { FaceSmileIcon } from '@heroicons/react/24/outline';

export default function NurseLoginPage() {
  const router = useRouter();
  const { login } = useUserStore();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // Mock 登录延迟
    await new Promise((resolve) => setTimeout(resolve, 800));

    // Mock 用户数据
    login({
      id: 'N001',
      role: 'nurse',
      name: '李护士',
      department: '心内科',
      avatar: '',
    });

    router.push('/nurse/dashboard');
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo 和标题 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-primary rounded-2xl mb-4">
            <span className="text-3xl text-white font-bold">医</span>
          </div>
          <h1 className="text-3xl font-serif font-medium text-foreground mb-2">
            智能护理评估<span className="text-primary italic">系统</span>
          </h1>
          <p className="text-foreground-muted">医护端登录</p>
        </div>

        {/* 登录表单 */}
        <Card>
          <CardHeader>
            <CardTitle>欢迎回来</CardTitle>
            <CardDescription>请使用您的工号和密码登录</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleLogin} className="space-y-4">
              <Input
                label="工号"
                type="text"
                autoComplete="username"
                placeholder="请输入工号"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
              <Input
                label="密码"
                type="password"
                autoComplete="current-password"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <Button type="submit" className="w-full" loading={loading}>
                登录
              </Button>
            </form>

            {/* 快速登录提示 */}
            <div className="mt-5 grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setUsername('N001');
                  setPassword('123456');
                }}
              >
                填充演示账号
              </Button>
              <Button type="button" variant="outline" size="sm" disabled>
                <FaceSmileIcon className="w-4 h-4 mr-1" />
                人脸识别占位
              </Button>
            </div>
            <div className="mt-4 p-3 bg-primary-tint rounded-xl">
              <p className="text-xs text-foreground-muted text-center">
                演示账号 N001 / 123456；原型不执行真实身份认证
              </p>
            </div>
          </CardContent>
        </Card>

        {/* 患者端入口 */}
        <div className="mt-6 text-center">
          <a
            href="/patient"
            className="text-sm text-foreground-muted hover:text-primary transition-colors"
          >
            前往患者端 →
          </a>
        </div>
      </div>
    </div>
  );
}
