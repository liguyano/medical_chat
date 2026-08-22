'use client';

import { Suspense, useState } from 'react';
import Image from 'next/image';
import { useRouter, useSearchParams } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import { mockPatients } from '@/lib/mock/data';
import { patientDemoAccounts } from '@/lib/patient/demoAccounts';

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
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="text-center">
          <Image
            src="/assets/patient/states/loading.svg"
            alt=""
            width={80}
            height={80}
            className="mx-auto h-20 w-20"
          />
          <p className="mt-4 font-medium text-foreground-muted">
            正在加载身份核验…
          </p>
        </div>
      </div>
    </PatientLayout>
  );
}

function PatientVerifyContent() {
  const apiMode = runtimeConfig.dataMode === 'api';
  const router = useRouter();
  const searchParams = useSearchParams();
  const { tasks, setTasks, updateTask } = useTaskStore();
  const { login } = useUserStore();
  const [taskNo, setTaskNo] = useState(() => searchParams.get('taskNo') ?? '');
  const [idCardNo, setIdCardNo] = useState('');
  const [participantType, setParticipantType] = useState<'patient' | 'family'>('patient');
  const [relationship, setRelationship] = useState('女儿');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [scanToken, setScanToken] = useState('');
  const [scanOpen, setScanOpen] = useState(false);

  const fillDemo = (mode: 'ai' | 'form') => {
    const task = tasks.find((item) =>
      mode === 'ai'
        ? item.collectionMode === 'ai_dialogue'
        : item.collectionMode === 'traditional_form'
    );
    if (!task) return;
    const patient = mockPatients.find((item) => item.id === task.patientId);
    setTaskNo(task.taskNo);
    setIdCardNo(patient?.idCard ?? '');
    setError('');
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);

    if (apiMode) {
      try {
        const portal = await careRepository.verifyPatientTask({
          taskNo: taskNo.trim(),
          idCardSuffix: idCardNo.trim(),
        });
        setTasks(portal.tasks);
        login({
          id: portal.patient.id,
          role: 'patient',
          name: portal.patient.name,
          department: portal.encounter.department,
        });
        router.push('/patient/tasks');
      } catch (loginError) {
        setError(
          loginError instanceof Error
            ? loginError.message
            : '患者身份核验失败'
        );
      } finally {
        setLoading(false);
      }
      return;
    }

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

    if (patient.idCard !== idCardNo.trim()) {
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

  const handleScanVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!scanToken.trim()) return;
    setError('');
    setLoading(true);
    try {
      const portal = await careRepository.verifyPatientScanToken(scanToken.trim());
      setTasks(portal.tasks);
      login({
        id: portal.patient.id,
        role: 'patient',
        name: portal.patient.name,
        department: portal.encounter.department,
      });
      router.push('/patient/tasks');
    } catch (scanError) {
      setError(
        scanError instanceof Error ? scanError.message : '扫码核验失败，请重新扫码'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <PatientLayout>
      <div className="relative min-h-screen overflow-hidden px-[18px] pb-8 pt-9">
        <div
          className="pointer-events-none absolute inset-x-0 top-28 h-44 opacity-70"
          aria-hidden="true"
          style={{
            background:
              'radial-gradient(ellipse at 20% 70%, #ffe8d5 0 26%, transparent 27%), radial-gradient(ellipse at 72% 70%, #fff0df 0 34%, transparent 35%)',
          }}
        />

        <div className="relative z-10 pt-2 text-center">
          <PatientIcon
            name="brand-heart-cross"
            className="mx-auto h-[92px] w-[92px] text-primary"
          />
          <h1 className="mt-5 text-[32px] font-black leading-tight text-[#4a241c]">
            进入护理服务
          </h1>
          <div className="mt-3 flex items-center justify-center gap-3">
            <span className="h-px w-16 bg-[#efc9ae]" />
            <p className="text-lg font-bold">患者身份核验</p>
            <span className="h-px w-16 bg-[#efc9ae]" />
          </div>

          <div className="patient-card mt-6 overflow-hidden p-4">
            <form onSubmit={handleVerify} className="space-y-5">
              <div className="grid grid-cols-2 rounded-2xl border border-[#f0d6c3] bg-[#fffaf5] p-1">
                {(
                  [
                    ['patient', '患者本人'],
                    ['family', '家属协助'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setParticipantType(value)}
                    className={`min-h-12 rounded-[14px] text-[16px] font-bold transition ${
                      participantType === value
                        ? 'bg-gradient-to-r from-[#ff6949] to-[#ff5133] text-white shadow-sm'
                        : 'text-foreground-muted'
                    }`}
                    aria-pressed={participantType === value}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <label className="patient-field flex items-center gap-3 px-4">
                  <PatientIcon name="clipboard" className="text-[#8e745f]" />
                  <span className="shrink-0 text-[16px] font-bold">任务编号</span>
                  <input
                    value={taskNo}
                    onChange={(event) => setTaskNo(event.target.value)}
                    placeholder="请输入任务编号"
                    className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-foreground-placeholder"
                    required
                  />
              </label>

              <label className="patient-field flex items-center gap-3 px-4">
                <PatientIcon name="user" className="text-[#8e745f]" />
                <span className="shrink-0 text-[17px] font-bold">
                  证件号后四位
                </span>
                <input
                  value={idCardNo}
                  onChange={(event) => setIdCardNo(event.target.value)}
                  placeholder="请输入后四位"
                  maxLength={4}
                  className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-foreground-placeholder"
                  required
                />
              </label>

              {participantType === 'family' && (
                <label className="patient-field flex items-center gap-3 px-4">
                  <PatientIcon name="family" className="text-[#8e745f]" />
                  <span className="shrink-0 text-[16px] font-bold">与患者关系</span>
                  <select
                    value={relationship}
                    onChange={(event) => setRelationship(event.target.value)}
                    className="min-w-0 flex-1 bg-transparent text-right text-[15px] outline-none"
                  >
                    <option>女儿</option>
                    <option>儿子</option>
                    <option>配偶</option>
                    <option>其他家属</option>
                  </select>
                </label>
              )}

              {error && (
                <div
                  role="alert"
                  className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700"
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="patient-primary-button w-full"
              >
                <PatientIcon name="shield" className="h-5 w-5" />
                {loading ? '正在核验…' : '核验并进入'}
              </button>
            </form>

            <div className="my-4 flex items-center gap-3">
              <span className="h-px flex-1 bg-border" />
              <span className="text-xs text-foreground-muted">
                {apiMode ? '联调演示身份' : '快速体验'}
              </span>
              <span className="h-px flex-1 bg-border" />
            </div>

            {apiMode ? (
              <>
                <div className="grid grid-cols-2 gap-2">
                {patientDemoAccounts.slice(0, 2).map((account) => (
                    <button
                      key={account.idCardNo}
                      type="button"
                      onClick={() => {
                        setIdCardNo(account.idCardNo.slice(-4));
                        setError('');
                      }}
                      className="patient-outline-button min-h-11 text-sm"
                    >
                      填充{account.name}
                    </button>
                  ))}
                </div>
                {patientDemoAccounts.length > 2 && (
                  <details className="mt-2 rounded-2xl bg-[#fffaf5] px-3 py-2 text-sm">
                    <summary className="cursor-pointer font-bold text-foreground-muted">
                      更多联调演示身份
                    </summary>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {patientDemoAccounts.slice(2).map((account) => (
                        <button
                          key={account.idCardNo}
                          type="button"
                          onClick={() => {
                            setIdCardNo(account.idCardNo.slice(-4));
                            setError('');
                          }}
                          className="min-h-10 rounded-xl border border-[#efc9ae] bg-white px-2 text-xs font-bold text-primary"
                        >
                          填充{account.name}
                        </button>
                      ))}
                    </div>
                  </details>
                )}
              </>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  className="patient-outline-button min-h-11 text-sm"
                  onClick={() => fillDemo('ai')}
                >
                  AI 对话任务
                </button>
                <button
                  type="button"
                  className="patient-outline-button min-h-11 text-sm"
                  onClick={() => fillDemo('form')}
                >
                  传统问卷任务
                </button>
              </div>
            )}

            <button
              type="button"
              className="patient-outline-button mt-3 w-full"
              onClick={() => {
                setScanOpen((current) => !current);
                setError('');
              }}
            >
              <PatientIcon name="qr" />
              {scanOpen ? '关闭扫码核验' : '扫码进入'}
            </button>

            {scanOpen && (
              <form
                onSubmit={handleScanVerify}
                className="mt-3 rounded-2xl border border-[#f0d6c3] bg-[#fffaf5] p-3 text-left"
              >
                <label className="text-sm font-bold text-foreground-muted">
                  扫码后粘贴院内一次性令牌
                  <input
                    value={scanToken}
                    onChange={(event) => setScanToken(event.target.value)}
                    placeholder="等待二维码内容…"
                    className="patient-field mt-2 w-full px-3 text-sm outline-none"
                    minLength={24}
                    required
                  />
                </label>
                <button
                  type="submit"
                  disabled={loading}
                  className="patient-primary-button mt-3 w-full"
                >
                  {loading ? '正在核验…' : '核验扫码令牌'}
                </button>
                <p className="mt-2 text-xs leading-5 text-foreground-muted">
                  相机权限未开启时可粘贴二维码内容；令牌只能使用一次，过期后请联系护士重新生成。
                </p>
              </form>
            )}
          </div>

          <p className="mt-4 flex items-center justify-center gap-2 text-sm text-foreground-muted">
            <PatientIcon name="shield" className="h-4 w-4" />
            信息仅用于护理评估
          </p>

          {apiMode && (
            <div className="mt-3 rounded-2xl bg-[#edf6ff] p-3 text-left text-xs leading-5 text-[#3c6594]">
              任务编号和证件后四位仅用于确认本次在院身份；登录后由患者专用接口加载本人护理任务。
            </div>
          )}
        </div>
      </div>
    </PatientLayout>
  );
}
