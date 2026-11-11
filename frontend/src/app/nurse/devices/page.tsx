'use client';

import { useEffect, useState } from 'react';
import NurseLayout from '@/components/layout/NurseLayout';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card } from '@/components/shared/Card';
import { apiRequest } from '@/lib/api/httpClient';
import { runtimeConfig } from '@/lib/runtime/config';

type Device = { device_id: string; online: boolean };
type Registration = { device_id: string; requested_at: string };
type Snapshot = { devices: Device[]; registrations: Registration[] } | { error: true };

export default function NurseDevicesPage() {
  const apiMode = runtimeConfig.dataMode === 'api';
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string>();
  const [code, setCode] = useState('');
  const [approving, setApproving] = useState(false);
  const [approvalError, setApprovalError] = useState('');

  useEffect(() => {
    if (!apiMode) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function load() {
      try {
        const options = { signal: controller.signal, cache: 'no-store' as const };
        const [devices, registrations] = await Promise.all([
          apiRequest<Device[]>('/api/tasks/devices', options),
          apiRequest<Registration[]>('/api/device/registrations', options),
        ]);
        if (!controller.signal.aborted) setSnapshot({ devices, registrations });
      } catch {
        if (!controller.signal.aborted) setSnapshot({ error: true });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 5000);
      }
    }

    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [apiMode, refresh]);

  const devices = snapshot && 'devices' in snapshot ? snapshot.devices : undefined;
  const registrations = snapshot && 'registrations' in snapshot ? snapshot.registrations : undefined;
  const online = devices?.filter((device) => device.online).length ?? 0;

  async function approve(deviceId: string) {
    setApproving(true);
    setApprovalError('');
    try {
      await apiRequest(`/api/device/registrations/${encodeURIComponent(deviceId)}/approve`, {
        method: 'POST',
        body: { verification_code: code.trim() },
      });
      setSelected(undefined);
      setRefresh((value) => value + 1);
    } catch (error) {
      setApprovalError(error instanceof Error ? error.message : '审批失败，请重试。');
    } finally {
      setApproving(false);
    }
  }

  return (
    <NurseLayout>
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-3xl">设备管理</h1>
        {apiMode && (
          <Button variant="outline" onClick={() => setRefresh((value) => value + 1)}>
            刷新状态
          </Button>
        )}
      </div>

      {devices && (
        <div className="mb-6 grid grid-cols-3 gap-3">
          {[
            { label: '已登记', count: devices.length },
            { label: '在线', count: online },
            { label: '离线', count: devices.length - online },
          ].map(({ label, count }) => (
            <Card key={label} padding="md">
              <p className="text-sm text-foreground-muted">{label}</p>
              <p className="mt-1 text-3xl">{count}</p>
            </Card>
          ))}
        </div>
      )}

      {registrations && (
        <Card padding="lg" className="mb-6">
          <h2 className="mb-4 text-xl">待登记申请</h2>
          {registrations.length === 0 && <p className="text-foreground-muted">暂无待审批设备。</p>}
          <ul className="divide-y divide-border">
            {registrations.map((registration) => (
              <li key={registration.device_id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{registration.device_id}</p>
                    <p className="text-sm text-foreground-muted">
                      {new Date(registration.requested_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                  <Button variant="outline" disabled={approving} onClick={() => {
                    setSelected(registration.device_id);
                    setCode('');
                    setApprovalError('');
                  }}>
                    审批
                  </Button>
                </div>
                {selected === registration.device_id && (
                  <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={(event) => {
                    event.preventDefault();
                    void approve(registration.device_id);
                  }}>
                    <label className="text-sm">
                      设备核对码
                      <input
                        className="mt-1 block rounded-xl border border-border px-3 py-2"
                        value={code}
                        maxLength={8}
                        autoComplete="off"
                        onChange={(event) => setCode(event.target.value)}
                        placeholder="输入设备显示的 8 位码"
                      />
                    </label>
                    <Button type="submit" loading={approving} disabled={!/^[0-9a-f]{8}$/i.test(code.trim())}>
                      同意登记
                    </Button>
                    {approvalError && <p role="alert" className="text-danger">{approvalError}</p>}
                  </form>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card padding="lg">
        <h2 className="mb-4 text-xl">嵌入式设备</h2>
        {!apiMode ? (
          <p className="text-foreground-muted">连接后端后可查看设备连接状态。</p>
        ) : !snapshot ? (
          <p role="status">正在读取设备状态…</p>
        ) : !devices ? (
          <p role="alert" className="text-danger">设备状态获取失败，请刷新重试。</p>
        ) : devices.length === 0 ? (
          <p className="text-foreground-muted">尚未登记设备。</p>
        ) : (
          <>
            {online === 0 && <p className="mb-4 text-foreground-muted">当前没有设备连接。</p>}
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-foreground-muted">
                <tr>
                  <th scope="col" className="pb-3 font-medium">设备 ID</th>
                  <th scope="col" className="pb-3 font-medium">连接状态</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {devices.map((device) => (
                  <tr key={device.device_id}>
                    <td className="py-3 pr-4 break-all">{device.device_id}</td>
                    <td className="py-3">
                      <Badge variant={device.online ? 'success' : 'default'}>
                        {device.online ? '在线' : '离线'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Card>
    </NurseLayout>
  );
}
