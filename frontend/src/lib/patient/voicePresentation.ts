export type VoicePresentationState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'transcribing'
  | 'thinking'
  | 'speaking'
  | 'paused'
  | 'error'
  | 'text_fallback'
  | 'closed';

export interface VoicePresentation {
  title: string;
  detail: string;
  color: string;
}

export const VOICE_PRESENTATIONS: Record<
  VoicePresentationState,
  VoicePresentation
> = {
  idle: {
    title: '点击开始说话',
    detail: '点击后才会使用麦克风',
    color: '#c4612f',
  },
  connecting: {
    title: '正在连接',
    detail: '正在准备安全的语音通道',
    color: '#4ba7a3',
  },
  listening: {
    title: '请说话',
    detail: '说完后点击“结束回答”',
    color: '#4ba7a3',
  },
  transcribing: {
    title: '正在识别',
    detail: '正在整理您刚才说的话',
    color: '#4ba7a3',
  },
  thinking: {
    title: 'AI 正在回答',
    detail: '小医正在思考，请稍候',
    color: '#5b8def',
  },
  speaking: {
    title: 'AI 正在播报',
    detail: '您可以随时打断播报',
    color: '#3dad82',
  },
  paused: {
    title: '语音已暂停',
    detail: '仍可切换到文字回答',
    color: '#5b8def',
  },
  error: {
    title: '语音出现异常',
    detail: '已为您保留文字回答',
    color: '#e5a146',
  },
  text_fallback: {
    title: '语音异常，已切换文字',
    detail: '您可以通过文字继续评估',
    color: '#e5a146',
  },
  closed: {
    title: '语音已关闭',
    detail: '需要时可重新开启语音',
    color: '#756d66',
  },
};

export function getVoicePresentation(
  state: VoicePresentationState
): VoicePresentation {
  return VOICE_PRESENTATIONS[state];
}
