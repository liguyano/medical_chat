'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Input } from '@/components/shared/Input';
import { mockEncounters, mockPatients } from '@/lib/mock/data';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  MagnifyingGlassIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';

export default function NursePatientsPage() {
  const [keyword, setKeyword] = useState('');
  const tasks = useTaskStore((state) => state.tasks);
  const records = useMemo(
    () =>
      mockPatients
        .map((patient) => ({
          patient,
          encounter: mockEncounters.find((item) => item.patientId === patient.id),
          tasks: tasks.filter((task) => task.patientId === patient.id),
        }))
        .filter(({ patient, encounter }) => {
          const text = `${patient.name}${patient.patientNo}${encounter?.inpatientNo}${encounter?.bedNo}`.toLowerCase();
          return text.includes(keyword.toLowerCase());
        }),
    [keyword, tasks]
  );

  return (
    <NurseLayout>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-6">
        <div>
          <Badge variant="primary" size="sm">在院患者</Badge>
          <h1 className="text-3xl mt-2">患者<span className="text-primary italic">管理</span></h1>
          <p className="text-foreground-muted mt-1">查看住院记录、任务进度和异常提示</p>
        </div>
        <div className="w-full md:w-80">
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索姓名、住院号或床号"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {records.map(({ patient, encounter, tasks: patientTasks }) => {
          const pendingReview = patientTasks.filter((task) => task.taskStatus === 'pending_review').length;
          const handoff = patientTasks.some((task) => task.handoffRequired);
          return (
            <Link key={patient.id} href={`/nurse/patients/${patient.id}`}>
              <Card hover padding="lg">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-2xl bg-primary-tint text-primary flex items-center justify-center font-semibold">
                    {patient.name.slice(-1)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <h2 className="text-lg font-semibold">{patient.name}</h2>
                        <p className="text-sm text-foreground-muted">
                          {patient.gender === 'male' ? '男' : '女'} · {patient.age}岁 · {encounter?.bedNo}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        {handoff && <Badge variant="danger" size="sm">需介入</Badge>}
                        {pendingReview > 0 && <Badge variant="warning" size="sm">{pendingReview}项待复核</Badge>}
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                      <div className="rounded-xl bg-surface-secondary p-3">
                        <p className="text-xs text-foreground-muted">住院号</p>
                        <p className="font-medium mt-1">{encounter?.inpatientNo}</p>
                      </div>
                      <div className="rounded-xl bg-surface-secondary p-3">
                        <p className="text-xs text-foreground-muted">诊断快照</p>
                        <p className="font-medium mt-1 truncate">{encounter?.diagnosis}</p>
                      </div>
                    </div>
                    <p className="text-xs text-foreground-muted mt-3">
                      当前护理任务 {patientTasks.length} 项
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>

      {records.length === 0 && (
        <Card padding="lg" className="text-center">
          {keyword ? <MagnifyingGlassIcon className="w-12 h-12 mx-auto opacity-40" /> : <UserGroupIcon className="w-12 h-12 mx-auto opacity-40" />}
          <p className="mt-3 text-foreground-muted">没有找到符合条件的患者</p>
        </Card>
      )}
    </NurseLayout>
  );
}
