'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import PatientRecordForm from '@/components/patient/PatientRecordForm';
import { Badge } from '@/components/shared/Badge';
import { Card } from '@/components/shared/Card';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import type {
  PatientRecordInput,
  PatientWithEncounter,
} from '@/lib/repositories/types';
import { useUserStore } from '@/lib/stores/useUserStore';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';

export default function EditPatientPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const router = useRouter();
  const isAuthenticated = useUserStore((state) => state.isAuthenticated);
  const [record, setRecord] = useState<PatientWithEncounter>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

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

  const updatePatient = async (input: PatientRecordInput) => {
    setSubmitting(true);
    setError('');
    try {
      const updated = await careRepository.updatePatient(patientId, input);
      router.push(`/nurse/patients/${updated.patient.id}`);
    } catch (updateError) {
      setError(
        updateError instanceof Error ? updateError.message : '患者信息保存失败'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <NurseLayout>
      <Link
        href={`/nurse/patients/${patientId}`}
        className="mb-5 inline-flex items-center gap-2 text-foreground-muted"
      >
        <ArrowLeftIcon className="h-5 w-5" />
        返回患者详情
      </Link>
      <div className="mb-6">
        <Badge variant="primary" size="sm">
          院内患者档案
        </Badge>
        <h1 className="mt-2 text-3xl">
          编辑<span className="italic text-primary">患者信息</span>
        </h1>
        <p className="mt-1 text-foreground-muted">
          更新患者主档和本次住院记录；历史评估快照不会被改写
        </p>
      </div>
      {loading ? (
        <Card padding="lg" className="text-center text-foreground-muted">
          正在加载患者信息...
        </Card>
      ) : record ? (
        <PatientRecordForm
          mode="edit"
          initialRecord={record}
          submitting={submitting}
          serverError={error}
          onCancel={() => router.push(`/nurse/patients/${patientId}`)}
          onSubmit={updatePatient}
        />
      ) : (
        <Card padding="lg" className="text-center text-danger">
          {error || '患者住院记录不存在'}
        </Card>
      )}
    </NurseLayout>
  );
}
