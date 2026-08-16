'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Badge } from '@/components/shared/Badge';
import TaskCard from '@/components/task/TaskCard';
import { getEncounterByPatientId, getPatientById } from '@/lib/mock/data';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  ArrowLeftIcon,
  CalendarDaysIcon,
  MapPinIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';

export default function NursePatientDetailPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const patient = getPatientById(patientId);
  const encounter = getEncounterByPatientId(patientId);
  const allTasks = useTaskStore((state) => state.tasks);
  const tasks = allTasks.filter((task) => task.patientId === patientId);

  if (!patient || !encounter) {
    return (
      <NurseLayout>
        <Card padding="lg" className="text-center">患者住院记录不存在</Card>
      </NurseLayout>
    );
  }

  return (
    <NurseLayout>
      <Link href="/nurse/patients" className="inline-flex items-center gap-2 text-foreground-muted mb-5">
        <ArrowLeftIcon className="w-5 h-5" />
        返回患者列表
      </Link>

      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-3xl">{patient.name}</h1>
            <Badge variant="success">在院</Badge>
          </div>
          <p className="text-foreground-muted mt-1">
            {patient.gender === 'male' ? '男' : '女'} · {patient.age}岁 · 患者编号 {patient.patientNo}
          </p>
        </div>
        <Link href={`/nurse/tasks/create?patientId=${patient.id}`}>
          <Button>
            <PlusIcon className="w-5 h-5 mr-2" />
            创建评估任务
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card padding="lg" className="lg:col-span-2">
          <CardHeader><CardTitle>本次住院信息</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-foreground-muted">住院号</p>
                <p className="font-medium mt-1">{encounter.inpatientNo}</p>
              </div>
              <div>
                <p className="text-foreground-muted">病区床号</p>
                <p className="font-medium mt-1">{encounter.ward} · {encounter.bedNo}</p>
              </div>
              <div>
                <p className="text-foreground-muted">科室</p>
                <p className="font-medium mt-1">{encounter.department}</p>
              </div>
              <div className="col-span-2">
                <p className="text-foreground-muted">诊断快照</p>
                <p className="font-medium mt-1">{encounter.diagnosis}</p>
              </div>
              <div>
                <p className="text-foreground-muted">入院时间</p>
                <p className="font-medium mt-1">{new Date(encounter.admissionDate).toLocaleString('zh-CN')}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card padding="lg">
          <CardHeader><CardTitle>联系与位置</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex gap-3">
              <MapPinIcon className="w-5 h-5 text-primary" />
              <div><p className="text-foreground-muted">床位</p><p>{encounter.bedNo}</p></div>
            </div>
            <div className="flex gap-3">
              <CalendarDaysIcon className="w-5 h-5 text-primary" />
              <div><p className="text-foreground-muted">联系方式</p><p>{patient.phone}</p></div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-7">
        <h2 className="text-2xl mb-4">护理任务记录</h2>
        {tasks.length ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} href={`/nurse/tasks/${task.id}`} />
            ))}
          </div>
        ) : (
          <Card padding="lg" className="text-center text-foreground-muted">尚未创建护理任务</Card>
        )}
      </div>
    </NurseLayout>
  );
}
