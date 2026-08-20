'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/shared/Card';
import TaskCard from '@/components/task/TaskCard';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import type { PatientWithEncounter } from '@/lib/repositories/types';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import {
  ArrowLeftIcon,
  CalendarDaysIcon,
  ClipboardDocumentListIcon,
  ExclamationTriangleIcon,
  MapPinIcon,
  PencilSquareIcon,
  PhoneIcon,
  PlusIcon,
  ShieldCheckIcon,
  UserIcon,
} from '@heroicons/react/24/outline';

function statusPresentation(
  status: PatientWithEncounter['encounter']['encounterStatus']
) {
  if (status === 'in_hospital') {
    return { label: '在院', variant: 'success' as const };
  }
  if (status === 'pending_admission') {
    return { label: '待入院', variant: 'warning' as const };
  }
  if (status === 'cancelled') {
    return { label: '已取消', variant: 'default' as const };
  }
  return { label: '已出院', variant: 'default' as const };
}

function displayDateTime(value?: string) {
  if (!value) return '未记录';
  return new Date(value).toLocaleString('zh-CN');
}

export default function NursePatientDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const isAuthenticated = useUserStore((state) => state.isAuthenticated);
  const allTasks = useTaskStore((state) => state.tasks);
  const [record, setRecord] = useState<PatientWithEncounter>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const tasks = useMemo(
    () => allTasks.filter((task) => task.patientId === patientId),
    [allTasks, patientId]
  );

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    void careRepository
      .getPatient(patientId, controller.signal)
      .then(setRecord)
      .catch((loadError) => {
        if (!isRequestCancelled(loadError)) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : '患者信息加载失败'
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => abortRequest(controller);
  }, [isAuthenticated, patientId]);

  if (loading) {
    return (
      <NurseLayout>
        <Card padding="lg" className="text-center text-foreground-muted">
          正在加载患者信息...
        </Card>
      </NurseLayout>
    );
  }

  if (!record) {
    return (
      <NurseLayout>
        <Card padding="lg" className="text-center text-danger">
          {error || '患者住院记录不存在'}
        </Card>
      </NurseLayout>
    );
  }

  const { patient, encounter, taskSummary } = record;
  const status = statusPresentation(encounter.encounterStatus);

  return (
    <NurseLayout>
      <Link
        href="/nurse/patients"
        className="mb-5 inline-flex items-center gap-2 text-foreground-muted"
      >
        <ArrowLeftIcon className="h-5 w-5" />
        返回患者列表
      </Link>

      <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl">{patient.name}</h1>
            <Badge variant={status.variant}>{status.label}</Badge>
            {taskSummary?.handoffRequired && (
              <Badge variant="danger">需人工介入</Badge>
            )}
          </div>
          <p className="mt-1 text-foreground-muted">
            {patient.gender === 'male'
              ? '男'
              : patient.gender === 'female'
                ? '女'
                : '其他'}{' '}
            · {patient.age}岁 · 患者编号 {patient.patientNo}
            {patient.hisPatientId ? ` · HIS ${patient.hisPatientId}` : ''}
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Link href={`/nurse/patients/${patient.id}/edit`}>
            <Button variant="outline" className="w-full sm:w-auto">
              <PencilSquareIcon className="mr-2 h-5 w-5" />
              编辑患者
            </Button>
          </Link>
          {encounter.encounterStatus === 'in_hospital' && (
            <Link href={`/nurse/tasks/create?patientId=${patient.id}`}>
              <Button className="w-full sm:w-auto">
                <PlusIcon className="mr-2 h-5 w-5" />
                创建评估任务
              </Button>
            </Link>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card padding="lg" className="lg:col-span-2">
          <CardHeader>
            <CardTitle>本次住院信息</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 md:grid-cols-3">
              <div>
                <p className="text-foreground-muted">住院号</p>
                <p className="mt-1 font-medium">{encounter.inpatientNo}</p>
              </div>
              <div>
                <p className="text-foreground-muted">病区床号</p>
                <p className="mt-1 font-medium">
                  {encounter.ward} · {encounter.bedNo}
                </p>
              </div>
              <div>
                <p className="text-foreground-muted">科室</p>
                <p className="mt-1 font-medium">
                  {encounter.department}
                  {encounter.departmentCode
                    ? `（${encounter.departmentCode}）`
                    : ''}
                </p>
              </div>
              <div>
                <p className="text-foreground-muted">入院来源</p>
                <p className="mt-1 font-medium">
                  {encounter.admissionSource || '未记录'}
                </p>
              </div>
              <div>
                <p className="text-foreground-muted">护理级别</p>
                <p className="mt-1 font-medium">
                  {encounter.nursingLevel || '未记录'}
                </p>
              </div>
              <div>
                <p className="text-foreground-muted">医保类别</p>
                <p className="mt-1 font-medium">
                  {encounter.insuranceType || '未记录'}
                </p>
              </div>
              <div className="sm:col-span-2 md:col-span-3">
                <p className="text-foreground-muted">诊断快照</p>
                <p className="mt-1 font-medium">
                  {encounter.diagnosis || '未记录'}
                </p>
              </div>
              <div>
                <p className="text-foreground-muted">入院时间</p>
                <p className="mt-1 font-medium">
                  {displayDateTime(encounter.admissionDate)}
                </p>
              </div>
              <div>
                <p className="text-foreground-muted">出院时间</p>
                <p className="mt-1 font-medium">
                  {displayDateTime(encounter.dischargeDate)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card padding="lg">
          <CardHeader>
            <CardTitle>联系与身份</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex gap-3">
              <PhoneIcon className="h-5 w-5 shrink-0 text-primary" />
              <div>
                <p className="text-foreground-muted">联系电话</p>
                <p>{patient.phone || '未记录'}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <UserIcon className="h-5 w-5 shrink-0 text-primary" />
              <div>
                <p className="text-foreground-muted">身份证</p>
                <p>{patient.idCard || '未记录'}</p>
              </div>
            </div>
            <div className="flex gap-3">
              <ShieldCheckIcon className="h-5 w-5 shrink-0 text-primary" />
              <div>
                <p className="text-foreground-muted">紧急联系人</p>
                <p>
                  {patient.emergencyContactName || '未记录'}
                  {patient.emergencyContactRelation
                    ? `（${patient.emergencyContactRelation}）`
                    : ''}
                </p>
                {patient.emergencyContactPhone && (
                  <p className="text-foreground-muted">
                    {patient.emergencyContactPhone}
                  </p>
                )}
              </div>
            </div>
            <div className="flex gap-3">
              <MapPinIcon className="h-5 w-5 shrink-0 text-primary" />
              <div>
                <p className="text-foreground-muted">家庭住址</p>
                <p>{patient.address || '未记录'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card padding="lg" className="lg:col-span-2">
          <CardHeader>
            <CardTitle>临床安全摘要</CardTitle>
          </CardHeader>
          <CardContent>
            <div
              className={`flex items-start gap-3 rounded-xl p-4 ${
                encounter.allergySummary
                  ? 'bg-amber-50 text-amber-900'
                  : 'bg-emerald-50 text-emerald-900'
              }`}
            >
              <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <p className="font-medium">过敏信息</p>
                <p className="mt-1 text-sm">
                  {encounter.allergySummary || '当前未记录已知过敏'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card padding="lg">
          <CardHeader>
            <CardTitle>护理任务摘要</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-3 gap-3 text-center">
            <div className="rounded-xl bg-surface-secondary p-3">
              <p className="text-2xl font-semibold">{taskSummary?.total ?? tasks.length}</p>
              <p className="text-xs text-foreground-muted">全部</p>
            </div>
            <div className="rounded-xl bg-surface-secondary p-3">
              <p className="text-2xl font-semibold">
                {taskSummary?.inProgress ?? 0}
              </p>
              <p className="text-xs text-foreground-muted">进行中</p>
            </div>
            <div className="rounded-xl bg-surface-secondary p-3">
              <p className="text-2xl font-semibold">
                {taskSummary?.pendingReview ?? 0}
              </p>
              <p className="text-xs text-foreground-muted">待复核</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-7">
        <div className="mb-4 flex items-center gap-2">
          <ClipboardDocumentListIcon className="h-6 w-6 text-primary" />
          <h2 className="text-2xl">护理任务记录</h2>
        </div>
        {tasks.length ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                href={`/nurse/tasks/${task.id}`}
              />
            ))}
          </div>
        ) : (
          <Card padding="lg" className="text-center text-foreground-muted">
            <CalendarDaysIcon className="mx-auto mb-2 h-8 w-8 opacity-50" />
            尚未创建护理任务
          </Card>
        )}
      </div>
    </NurseLayout>
  );
}
