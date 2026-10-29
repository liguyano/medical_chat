import { useEffect, useState } from 'react';
import type { VoiceCaptureDiagnostics } from '@/lib/audio/voiceCaptureStats';

export function VoiceDiagnosticsPanel({ data }: { data: VoiceCaptureDiagnostics | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const age = data?.lastFrameAt ? Math.max(0, Math.floor((now - data.lastFrameAt) / 1000)) : null;
  const hint = !data ? '开启语音后显示检测数据' : data.trackState !== 'live' ? '当前麦克风采集未开启或已停止' : !data.lastFrameAt ? '尚未采集到音频帧'
    : age !== null && age > 2 ? '音频帧已停止更新'
    : data.muted || !data.enabled ? '音轨被静音或禁用'
    : data.rms === 0 ? '当前采集为静音，说话时观察数值是否变化'
    : '检测到声音能量，尚不代表模型已识别';
  return <section className="rounded-2xl border border-border bg-surface p-4 text-sm" aria-label="麦克风实时检测">
    <h2 className="font-bold">麦克风实时检测</h2>
    <p className="my-3 text-xs text-foreground-muted">{hint}</p>
    <meter min={0} max={32768} value={data?.rms ?? 0} aria-label="麦克风音量" className="w-full" />
    <dl className="mt-3 space-y-2 break-words">
      <div>输入设备：{data?.device ?? '尚未开启'}</div>
      <div>音轨：{data?.trackState ?? '—'} / {data?.muted ? '静音' : '未静音'} / {data?.enabled ? '启用' : '未启用'}</div>
      <div>采集引擎：{data?.contextState ?? '—'}</div>
      <div>采样率：{data?.sampleRate ?? 0} Hz</div>
      <div>音量 RMS：{data?.rms ?? 0} / 峰值：{data?.peak ?? 0}</div>
      <div>采集帧数：{data?.frames ?? 0}</div>
      <div>已提交发送：{data?.sentBytes ?? 0} 字节</div>
      <div>最近音频帧：{age === null ? '尚无' : `${age} 秒前`}</div>
      <div>语音连接：{data?.socketState === 1 ? '已打开' : '未打开'}</div>
    </dl>
    <p className="mt-4 text-xs text-foreground-muted">只观察当前网页采集，不新增录音或上传。持续说话而音量为0，说明网页未采到有效声音。</p>
  </section>;
}
