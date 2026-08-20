'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import NurseLayout from '@/components/layout/NurseLayout';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card } from '@/components/shared/Card';
import { Input } from '@/components/shared/Input';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import type {
  PatientListFilters,
  PatientWithEncounter,
} from '@/lib/repositories/types';
import { useUserStore } from '@/lib/stores/useUserStore';
import {
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';

const selectClassName =
  'rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary';

function encounterStatusLabel(
  status: PatientWithEncounter['encounter']['encounterStatus']
) {
  if (status === 'pending_admission') return '待入院';
  if (status === 'in_hospital') return '在院';
  if (status === 'cancelled') return '取消';
  return '已出院';
}

function encounterStatusVariant(
  status: PatientWithEncounter['encounter']['encounterStatus']
) {
  if (status === 'in_hospital') return 'success' as const;
  if (status === 'pending_admission') return 'warning' as const;
  return 'default' as const;
}

export default function NursePatientsPage() {
  const isAuthenticated = useUserStore((state) => state.isAuthenticated);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] =
    useState<NonNullable<PatientListFilters['status']>>('在院');
  const [departmentName, setDepartmentName] = useState('');
  const [wardName, setWardName] = useState('');
  const [records, setRecords] = useState<PatientWithEncounter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => {
      setLoading(true);
      setError('');
      void careRepository
        .listPatients(
          { keyword, status, departmentName, wardName },
          controller.signal
        )
        .then(setRecords)
        .catch((loadError) => {
          if (!isRequestCancelled(loadError)) {
            setRecords([]);
            setError(
              loadError instanceof Error
                ? loadError.message
                : '患者列表加载失败'
            );
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);
    return () => {
      globalThis.clearTimeout(timeout);
      abortRequest(controller);
    };
  }, [departmentName, isAuthenticated, keyword, status, wardName]);

  const departments = useMemo(
    () =>
      Array.from(
        new Set(
          records.map((item) => item.encounter.department).filter(Boolean)
        )
      ).sort(),
    [records]
  );
  const wards = useMemo(
    () =>
      Array.from(
        new Set(records.map((item) => item.encounter.ward).filter(Boolean))
      ).sort(),
    [records]
  );

  return (
    <NurseLayout>
      <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="primary" size="sm">
              院内患者主索引
            </Badge>
            <IntegrationStatus compact />
          </div>
          <h1 className="mt-2 text-3xl">
            患者<span className="italic text-primary">管理</span>
          </h1>
          <p className="mt-1 text-foreground-muted">
            管理患者主档、住院过程、临床安全信息和护理任务
          </p>
        </div>
        <Link href="/nurse/patients/new">
          <Button className="w-full md:w-auto">
            <PlusIcon className="mr-2 h-5 w-5" />
            新增患者
          </Button>
        </Link>
      </div>

      <Card padding="lg" className="mb-5">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="姓名 / 患者号 / HIS ID / 住院号 / 床号"
          />
          <select
            aria-label="住院状态"
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as typeof status)
            }
            className={selectClassName}
          >
            <option value="">全部住院状态</option>
            <option value="待入院">待入院</option>
            <option value="在院">在院</option>
            <option value="已出院">已出院</option>
            <option value="取消">取消</option>
          </select>
          <select
            aria-label="科室"
            value={departmentName}
            onChange={(event) => {
              setDepartmentName(event.target.value);
              setWardName('');
            }}
            className={selectClassName}
          >
            <option value="">全部科室</option>
            {departmentName && !departments.includes(departmentName) && (
              <option value={departmentName}>{departmentName}</option>
            )}
            {departments.map((department) => (
              <option key={department} value={department}>
                {department}
              </option>
            ))}
          </select>
          <select
            aria-label="病区"
            value={wardName}
            onChange={(event) => setWardName(event.target.value)}
            className={selectClassName}
          >
            <option value="">全部病区</option>
            {wardName && !wards.includes(wardName) && (
              <option value={wardName}>{wardName}</option>
            )}
            {wards.map((ward) => (
              <option key={ward} value={ward}>
                {ward}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {error && (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <Card padding="lg" className="text-center text-foreground-muted">
          正在加载患者列表...
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {records.map(({ patient, encounter, taskSummary }) => (
            <Link key={patient.id} href={`/nurse/patients/${patient.id}`}>
              <Card hover padding="lg" className="h-full">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-primary-tint font-semibold text-primary">
                    {patient.name.slice(-1)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="text-lg font-semibold">
                            {patient.name}
                          </h2>
                          <Badge
                            variant={encounterStatusVariant(
                              encounter.encounterStatus
                            )}
                            size="sm"
                          >
                            {encounterStatusLabel(encounter.encounterStatus)}
                          </Badge>
                        </div>
                        <p className="mt-1 text-sm text-foreground-muted">
                          {patient.gender === 'male'
                            ? '男'
                            : patient.gender === 'female'
                              ? '女'
                              : '其他'}{' '}
                          · {patient.age}岁 · {encounter.ward}{' '}
                          {encounter.bedNo}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {taskSummary?.handoffRequired && (
                          <Badge variant="danger" size="sm">
                            需人工介入
                          </Badge>
                        )}
                        {(taskSummary?.pendingReview ?? 0) > 0 && (
                          <Badge variant="warning" size="sm">
                            {taskSummary?.pendingReview}项待复核
                          </Badge>
                        )}
                      </div>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
                      <div className="rounded-xl bg-surface-secondary p-3">
                        <p className="text-xs text-foreground-muted">住院号</p>
                        <p className="mt-1 truncate font-medium">
                          {encounter.inpatientNo}
                        </p>
                      </div>
                      <div className="rounded-xl bg-surface-secondary p-3">
                        <p className="text-xs text-foreground-muted">护理级别</p>
                        <p className="mt-1 truncate font-medium">
                          {encounter.nursingLevel || '未记录'}
                        </p>
                      </div>
                      <div className="col-span-2 rounded-xl bg-surface-secondary p-3">
                        <p className="text-xs text-foreground-muted">诊断快照</p>
                        <p className="mt-1 truncate font-medium">
                          {encounter.diagnosis || '未记录'}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-col gap-2 text-xs text-foreground-muted sm:flex-row sm:items-center sm:justify-between">
                      <p>
                        患者号 {patient.patientNo}
                        {patient.hisPatientId
                          ? ` · HIS ${patient.hisPatientId}`
                          : ''}
                      </p>
                      <p>
                        护理任务 {taskSummary?.total ?? 0} 项 · 进行中{' '}
                        {taskSummary?.inProgress ?? 0} 项
                      </p>
                    </div>
                    {encounter.allergySummary && (
                      <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
                        <ExclamationTriangleIcon className="mt-0.5 h-4 w-4 shrink-0" />
                        过敏：{encounter.allergySummary}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {!loading && records.length === 0 && !error && (
        <Card padding="lg" className="text-center">
          {keyword ? (
            <MagnifyingGlassIcon className="mx-auto h-12 w-12 opacity-40" />
          ) : (
            <UserGroupIcon className="mx-auto h-12 w-12 opacity-40" />
          )}
          <p className="mt-3 text-foreground-muted">
            没有找到符合条件的患者
          </p>
        </Card>
      )}
    </NurseLayout>
  );
}
