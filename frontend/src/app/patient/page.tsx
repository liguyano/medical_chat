'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Input } from '@/components/shared/Input';
import { Badge } from '@/components/shared/Badge';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import { mockPatients } from '@/lib/mock/data';
import {
  FaceSmileIcon,
  QrCodeIcon,
  ShieldCheckIcon,
  UserIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';

export default function PatientVerifyPage() {
  return (
    <Suspense fallback={<VerifyFallback />}>
      <PatientVerifyContent />
    </Suspense>
  );
}

function VerifyFallback() {
  return (
    <PatientLayout>
      <div className="min-h-screen flex items-center justify-center p-4">
        <p className="text-foreground-muted">正在加载身份核验...</p>
      </div>
    </PatientLayout>
  );
}

function PatientVerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { tasks, updateTask } = useTaskStore();
  const { login } = useUserStore();
  const [taskNo, setTaskNo] = useState(() => searchParams.get('taskNo') ?? '');
  const [idCardLastFour, setIdCardLastFour] = useState('');
  const [participantType, setParticipantType] = useState<'patient' | 'family'>('patient');
  const [relationship, setRelationship] = useState('女儿');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fillDemo = (mode: 'ai' | 'form') => {
    const task = tasks.find((item) =>
      mode === 'ai'
        ? item.collectionMode === 'ai_dialogue'
        : item.collectionMode === 'traditional_form'
    );
    if (!task) return;
    const patient = mockPatients.find((item) => item.id === task.patientId);
    setTaskNo(task.taskNo);
    setIdCardLastFour(patient?.idCard ?? '');
    setError('');
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    await new Promise((resolve) => setTimeout(resolve, 450));

    const task = tasks.find((item) => item.taskNo.toLowerCase() === taskNo.trim().toLowerCase());
    const patient = task
      ? mockPatients.find((item) => item.id === task.patientId)
      : undefined;

    if (!task || !patient) {
      setError('没有找到该任务，请检查任务编号');
      setLoading(false);
      return;
    }

    if (patient.idCard !== idCardLastFour.trim()) {
      setError('证件后四位与任务患者不匹配');
      setLoading(false);
      return;
    }

    updateTask(task.id, {
      participantType,
      participantName: participantType === 'patient' ? patient.name : `${patient.name}家属`,
      relationshipToPatient: participantType === 'family' ? relationship : undefined,
    });
    login({
      id: patient.id,
      role: 'patient',
      name: patient.name,
      department: task.department,
    });
    router.push('/patient/tasks');
  };

  return (
    <PatientLayout>
      <div className="min-h-screen bg-background px-4 py-8 flex items-center justify-center">
        <div className="w-full max-w-lg">
          <div className="text-center mb-7">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary text-white text-3xl font-bold mb-4">
              医
            </div>
            <div className="flex items-center justify-center gap-2 mb-2">
              <h1 className="text-3xl text-foreground">患者身份核验</h1>
              <Badge variant="primary" size="sm">演示数据</Badge>
            </div>
            <p className="text-sm text-foreground-muted">
              核验成功后仅展示本次住院对应的护理任务
            </p>
          </div>

          <Card padding="lg">
            <form onSubmit={handleVerify} className="space-y-5">
              <Input
                label="任务编号"
                value={taskNo}
                onChange={(event) => setTaskNo(event.target.value)}
                placeholder="例如 T2026080001"
                required
              />
              <Input
                label="证件号码后四位"
                value={idCardLastFour}
                onChange={(event) => setIdCardLastFour(event.target.value)}
                placeholder="请输入4位数字"
                maxLength={4}
                required
              />

              <div>
                <p className="text-sm font-medium text-foreground mb-3">本次参与人</p>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setParticipantType('patient')}
                    className={`p-4 rounded-xl border-2 text-left transition-colors ${
                      participantType === 'patient'
                        ? 'border-primary bg-primary-tint'
                        : 'border-border bg-surface'
                    }`}
                  >
                    <UserIcon className="w-5 h-5 text-primary mb-2" />
                    <span className="font-medium">患者本人</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setParticipantType('family')}
                    className={`p-4 rounded-xl border-2 text-left transition-colors ${
                      participantType === 'family'
                        ? 'border-primary bg-primary-tint'
                        : 'border-border bg-surface'
                    }`}
                  >
                    <UsersIcon className="w-5 h-5 text-primary mb-2" />
                    <span className="font-medium">家属协助</span>
                  </button>
                </div>
              </div>

              {participantType === 'family' && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1.5">
                    与患者关系
                  </label>
                  <select
                    value={relationship}
                    onChange={(event) => setRelationship(event.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-border bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option>女儿</option>
                    <option>儿子</option>
                    <option>配偶</option>
                    <option>其他家属</option>
                  </select>
                </div>
              )}

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <Button type="submit" loading={loading} className="w-full">
                <ShieldCheckIcon className="w-5 h-5 mr-2" />
                核验并进入
              </Button>
            </form>

            <div className="mt-6 pt-5 border-t border-border">
              <p className="text-xs text-foreground-muted text-center mb-3">快速填充演示身份</p>
              <div className="grid grid-cols-2 gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => fillDemo('ai')}>
                  AI对话任务
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => fillDemo('form')}>
                  传统问卷任务
                </Button>
              </div>
            </div>
          </Card>

          <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs text-foreground-muted">
            <div className="rounded-xl bg-surface-secondary p-3">
              <QrCodeIcon className="w-5 h-5 mx-auto mb-1" />
              扫码入口占位
            </div>
            <div className="rounded-xl bg-surface-secondary p-3">
              <FaceSmileIcon className="w-5 h-5 mx-auto mb-1" />
              人脸识别暂未开放
            </div>
            <div className="rounded-xl bg-surface-secondary p-3">
              <ShieldCheckIcon className="w-5 h-5 mx-auto mb-1" />
              信息仅用于护理评估
            </div>
          </div>
        </div>
      </div>
    </PatientLayout>
  );
}
