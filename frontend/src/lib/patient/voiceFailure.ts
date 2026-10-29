export type VoiceFailureStage = 'microphone' | 'connect' | 'network' | 'closed' | 'message' | 'server' | 'unsupported';

/** 只展示已知类别和短错误码，不直接显示供应商消息。 */
export function describeVoiceFailure(stage: VoiceFailureStage, code?: string): string {
  const safeCode = code && /^[A-Za-z0-9_-]{1,64}$/.test(code) ? code : 'UNKNOWN';
  let detail: string;
  let reference: string = safeCode;
  if (stage === 'microphone') {
    const reasons: Record<string, string> = {
      TrackEnded: '浏览器麦克风音轨已结束，自动恢复未能保持，请检查输入设备或其他程序是否占用。',
      NotAllowedError: '无法使用麦克风，请在浏览器设置中允许麦克风，并确认页面使用 HTTPS。',
      NotFoundError: '未找到可用麦克风，请连接麦克风后重试。',
      NotReadableError: '麦克风无法读取，可能被其他程序占用，请检查设备后重试。',
      OverconstrainedError: '麦克风不支持当前采集设置，请更换设备后重试。',
    };
    detail = reasons[safeCode] ?? '麦克风启动失败，具体原因待查，请检查设备与权限。';
    reference = `MIC_${safeCode}`;
  } else if (stage === 'server') {
    detail = safeCode === 'VOICE_UPSTREAM_FAILED'
      ? '后端与语音模型交互时发生异常，语音已中断，请联系维护人员查看日志。'
      : safeCode === 'VOICE_GATEWAY_ERROR'
        ? '后端语音服务处理失败，请联系维护人员查看日志。'
        : '语音服务返回错误，具体原因待查，请联系维护人员查看日志。';
  } else if (stage === 'unsupported') {
    detail = '当前浏览器无法采集麦克风，请使用支持麦克风的浏览器并通过 HTTPS 打开页面。';
    reference = 'MIC_UNSUPPORTED';
  } else if (stage === 'message') {
    detail = '语音消息或播放处理失败，请检查音频设备；具体原因待查。';
    reference = `VOICE_MESSAGE_${safeCode}`;
  } else if (stage === 'closed') {
    detail = '浏览器与语音服务的连接已断开，具体原因待查，请检查网络及后台日志。';
    reference = `WS_${safeCode}`;
  } else {
    detail = stage === 'connect'
      ? '浏览器未能连接语音服务，请检查网络和后端是否启动；具体原因待查。'
      : '浏览器语音连接发生错误，具体原因待查，请检查网络及后台日志。';
    reference = stage === 'connect' ? 'VOICE_CONNECT_FAILED' : 'VOICE_NETWORK_ERROR';
  }
  return `${detail} 可用文字继续。错误编号：${reference}`;
}
