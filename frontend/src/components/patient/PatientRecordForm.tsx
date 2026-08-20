'use client';

import { useMemo, useState } from 'react';
import { Button } from '@/components/shared/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/shared/Card';
import { Input } from '@/components/shared/Input';
import type {
  PatientRecordInput,
  PatientWithEncounter,
} from '@/lib/repositories/types';

interface PatientRecordFormProps {
  mode: 'create' | 'edit';
  initialRecord?: PatientWithEncounter;
  submitting?: boolean;
  serverError?: string;
  onCancel: () => void;
  onSubmit: (input: PatientRecordInput) => Promise<void>;
}

const fieldClassName =
  'w-full rounded-xl border border-border bg-surface px-4 py-2.5 text-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary';

function toLocalDateTime(value?: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function diagnosisValue(
  record: PatientWithEncounter | undefined,
  key: 'secondary' | 'risk_note'
): string {
  const value = record?.encounter.diagnosisSnapshot?.[key];
  if (Array.isArray(value)) return value.map(String).join('\n');
  return typeof value === 'string' ? value : '';
}

export default function PatientRecordForm({
  mode,
  initialRecord,
  submitting = false,
  serverError,
  onCancel,
  onSubmit,
}: PatientRecordFormProps) {
  const [form, setForm] = useState(() => ({
    hisPatientId: initialRecord?.patient.hisPatientId ?? '',
    name: initialRecord?.patient.name ?? '',
    gender: initialRecord?.patient.gender ?? ('female' as const),
    birthday: initialRecord?.patient.birthday ?? '',
    idCardNo: '',
    phone: initialRecord?.patient.phone ?? '',
    emergencyContactName: initialRecord?.patient.emergencyContactName ?? '',
    emergencyContactRelation:
      initialRecord?.patient.emergencyContactRelation ?? '',
    emergencyContactPhone:
      initialRecord?.patient.emergencyContactPhone ?? '',
    address: initialRecord?.patient.address ?? '',
    inpatientNo: initialRecord?.encounter.inpatientNo ?? '',
    departmentCode: initialRecord?.encounter.departmentCode ?? '',
    department: initialRecord?.encounter.department ?? '',
    ward: initialRecord?.encounter.ward ?? '',
    bedNo: initialRecord?.encounter.bedNo ?? '',
    admissionDate: toLocalDateTime(initialRecord?.encounter.admissionDate),
    dischargeDate: toLocalDateTime(initialRecord?.encounter.dischargeDate),
    encounterStatus:
      initialRecord?.encounter.encounterStatus ?? ('in_hospital' as const),
    primaryDiagnosis: initialRecord?.encounter.diagnosis ?? '',
    secondaryDiagnoses: diagnosisValue(initialRecord, 'secondary'),
    riskNote: diagnosisValue(initialRecord, 'risk_note'),
    admissionSource: initialRecord?.encounter.admissionSource ?? '门诊',
    nursingLevel: initialRecord?.encounter.nursingLevel ?? '二级护理',
    insuranceType: initialRecord?.encounter.insuranceType ?? '',
    allergySummary: initialRecord?.encounter.allergySummary ?? '',
  }));
  const [validationError, setValidationError] = useState('');

  const requiredFields = useMemo(
    () => [
      ['患者姓名', form.name],
      ['出生日期', form.birthday],
      ['联系电话', form.phone],
      ['住院号', form.inpatientNo],
      ['科室', form.department],
      ['病区', form.ward],
      ['床号', form.bedNo],
      ['入院时间', form.admissionDate],
      ['主要诊断', form.primaryDiagnosis],
      ...(mode === 'create' ? ([['身份证号', form.idCardNo]] as const) : []),
    ],
    [form, mode]
  );

  const update = (key: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    setValidationError('');
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = requiredFields.find(([, value]) => !value.trim());
    if (missing) {
      setValidationError(`请填写${missing[0]}`);
      return;
    }
    if (form.dischargeDate && form.encounterStatus === 'in_hospital') {
      setValidationError('已填写出院时间时，住院状态不能仍为“在院”');
      return;
    }
    await onSubmit({
      patient: {
        hisPatientId: form.hisPatientId.trim() || undefined,
        name: form.name.trim(),
        gender: form.gender,
        birthday: form.birthday,
        idCardNo: form.idCardNo.trim() || undefined,
        phone: form.phone.trim(),
        emergencyContactName:
          form.emergencyContactName.trim() || undefined,
        emergencyContactRelation:
          form.emergencyContactRelation.trim() || undefined,
        emergencyContactPhone:
          form.emergencyContactPhone.trim() || undefined,
        address: form.address.trim() || undefined,
      },
      encounter: {
        id: initialRecord?.encounter.id,
        inpatientNo: form.inpatientNo.trim(),
        departmentCode: form.departmentCode.trim() || undefined,
        department: form.department.trim(),
        ward: form.ward.trim(),
        bedNo: form.bedNo.trim(),
        admissionDate: new Date(form.admissionDate).toISOString(),
        dischargeDate: form.dischargeDate
          ? new Date(form.dischargeDate).toISOString()
          : undefined,
        encounterStatus: form.encounterStatus,
        primaryDiagnosis: form.primaryDiagnosis.trim(),
        secondaryDiagnoses: form.secondaryDiagnoses
          .split(/\r?\n|、/)
          .map((item) => item.trim())
          .filter(Boolean),
        riskNote: form.riskNote.trim() || undefined,
        admissionSource: form.admissionSource.trim() || undefined,
        nursingLevel: form.nursingLevel.trim() || undefined,
        insuranceType: form.insuranceType.trim() || undefined,
        allergySummary: form.allergySummary.trim() || undefined,
      },
    });
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <Card padding="lg">
        <CardHeader>
          <CardTitle>患者基本信息</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Input
            label="患者姓名 *"
            value={form.name}
            onChange={(event) => update('name', event.target.value)}
          />
          <label className="text-sm font-medium">
            <span className="mb-1.5 block">性别 *</span>
            <select
              value={form.gender}
              onChange={(event) => update('gender', event.target.value)}
              className={fieldClassName}
            >
              <option value="female">女</option>
              <option value="male">男</option>
              <option value="other">其他</option>
            </select>
          </label>
          <Input
            label="出生日期 *"
            type="date"
            value={form.birthday}
            onChange={(event) => update('birthday', event.target.value)}
          />
          <Input
            label={mode === 'create' ? '身份证号 *' : '身份证号（留空不修改）'}
            value={form.idCardNo}
            onChange={(event) => update('idCardNo', event.target.value)}
            placeholder={
              mode === 'edit'
                ? initialRecord?.patient.idCard ?? '留空保持原身份证号'
                : '仅用于患者身份核验'
            }
          />
          <Input
            label="HIS 患者 ID"
            value={form.hisPatientId}
            onChange={(event) => update('hisPatientId', event.target.value)}
          />
          <Input
            label="联系电话 *"
            value={form.phone}
            onChange={(event) => update('phone', event.target.value)}
          />
          <Input
            label="紧急联系人"
            value={form.emergencyContactName}
            onChange={(event) =>
              update('emergencyContactName', event.target.value)
            }
          />
          <Input
            label="与患者关系"
            value={form.emergencyContactRelation}
            onChange={(event) =>
              update('emergencyContactRelation', event.target.value)
            }
          />
          <Input
            label="紧急联系电话"
            value={form.emergencyContactPhone}
            onChange={(event) =>
              update('emergencyContactPhone', event.target.value)
            }
          />
          <div className="md:col-span-2 lg:col-span-3">
            <Input
              label="家庭住址"
              value={form.address}
              onChange={(event) => update('address', event.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>本次住院信息</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Input
            label="住院号 *"
            value={form.inpatientNo}
            onChange={(event) => update('inpatientNo', event.target.value)}
          />
          <Input
            label="科室编码"
            value={form.departmentCode}
            onChange={(event) => update('departmentCode', event.target.value)}
          />
          <Input
            label="科室 *"
            value={form.department}
            onChange={(event) => update('department', event.target.value)}
          />
          <Input
            label="病区 *"
            value={form.ward}
            onChange={(event) => update('ward', event.target.value)}
          />
          <Input
            label="床号 *"
            value={form.bedNo}
            onChange={(event) => update('bedNo', event.target.value)}
          />
          <label className="text-sm font-medium">
            <span className="mb-1.5 block">住院状态 *</span>
            <select
              value={form.encounterStatus}
              onChange={(event) =>
                update('encounterStatus', event.target.value)
              }
              className={fieldClassName}
            >
              <option value="pending_admission">待入院</option>
              <option value="in_hospital">在院</option>
              <option value="discharged">已出院</option>
              <option value="cancelled">取消</option>
            </select>
          </label>
          <Input
            label="入院时间 *"
            type="datetime-local"
            value={form.admissionDate}
            onChange={(event) => update('admissionDate', event.target.value)}
          />
          <Input
            label="出院时间"
            type="datetime-local"
            value={form.dischargeDate}
            onChange={(event) => update('dischargeDate', event.target.value)}
          />
          <Input
            label="入院来源"
            value={form.admissionSource}
            onChange={(event) => update('admissionSource', event.target.value)}
            placeholder="门诊 / 急诊 / 转院"
          />
          <Input
            label="护理级别"
            value={form.nursingLevel}
            onChange={(event) => update('nursingLevel', event.target.value)}
            placeholder="特级 / 一级 / 二级 / 三级护理"
          />
          <Input
            label="医保类别"
            value={form.insuranceType}
            onChange={(event) => update('insuranceType', event.target.value)}
          />
        </CardContent>
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>临床与安全摘要</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <Input
              label="主要诊断 *"
              value={form.primaryDiagnosis}
              onChange={(event) =>
                update('primaryDiagnosis', event.target.value)
              }
            />
          </div>
          <label className="text-sm font-medium">
            <span className="mb-1.5 block">其他诊断（每行一项）</span>
            <textarea
              rows={4}
              value={form.secondaryDiagnoses}
              onChange={(event) =>
                update('secondaryDiagnoses', event.target.value)
              }
              className={fieldClassName}
            />
          </label>
          <label className="text-sm font-medium">
            <span className="mb-1.5 block">风险备注</span>
            <textarea
              rows={4}
              value={form.riskNote}
              onChange={(event) => update('riskNote', event.target.value)}
              className={fieldClassName}
            />
          </label>
          <div className="md:col-span-2">
            <label className="text-sm font-medium">
              <span className="mb-1.5 block">过敏信息摘要</span>
              <textarea
                rows={3}
                value={form.allergySummary}
                onChange={(event) =>
                  update('allergySummary', event.target.value)
                }
                className={fieldClassName}
                placeholder="无已知过敏，或填写过敏原与既往反应"
              />
            </label>
          </div>
        </CardContent>
      </Card>

      {(validationError || serverError) && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {validationError || serverError}
        </div>
      )}

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" loading={submitting}>
          {mode === 'create' ? '保存并创建患者' : '保存患者信息'}
        </Button>
      </div>
    </form>
  );
}
