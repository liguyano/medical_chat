'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import PatientRecordForm from '@/components/patient/PatientRecordForm';
import { Badge } from '@/components/shared/Badge';
import { careRepository } from '@/lib/repositories';
import type { PatientRecordInput } from '@/lib/repositories/types';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';

export default function NewPatientPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const createPatient = async (input: PatientRecordInput) => {
    setSubmitting(true);
    setError('');
    try {
      const record = await careRepository.createPatient(input);
      router.push(`/nurse/patients/${record.patient.id}`);
    } catch (createError) {
      setError(
        createError instanceof Error ? createError.message : '新增患者失败'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <NurseLayout>
      <Link
        href="/nurse/patients"
        className="mb-5 inline-flex items-center gap-2 text-foreground-muted"
      >
        <ArrowLeftIcon className="h-5 w-5" />
        返回患者列表
      </Link>
      <div className="mb-6">
        <Badge variant="primary" size="sm">
          建立院内患者档案
        </Badge>
        <h1 className="mt-2 text-3xl">
          新增<span className="italic text-primary">患者</span>
        </h1>
        <p className="mt-1 text-foreground-muted">
          一次录入患者主档、本次住院信息和临床安全摘要
        </p>
      </div>
      <PatientRecordForm
        mode="create"
        submitting={submitting}
        serverError={error}
        onCancel={() => router.push('/nurse/patients')}
        onSubmit={createPatient}
      />
    </NurseLayout>
  );
}
