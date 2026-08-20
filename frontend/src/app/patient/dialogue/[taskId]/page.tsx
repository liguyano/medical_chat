'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import ChatBubble from '@/components/chat/ChatBubble';
import ChatInput from '@/components/chat/ChatInput';
import ConsentInteractionCard from '@/components/chat/ConsentInteractionCard';
import EducationMaterialCard from '@/components/chat/EducationMaterialCard';
import HandoffHistoryCard from '@/components/chat/HandoffHistoryCard';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card } from '@/components/shared/Card';
import { Progress } from '@/components/shared/Progress';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { useRealtimeStream } from '@/hooks/useRealtimeStream';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { buildDialogueHistoryTimeline } from '@/lib/dialogue/historyTimeline';
import { createClientInvocationId } from '@/lib/clientInvocation';
import { getStructuredAnswerDisplayValue } from '@/lib/structuredAnswer';
import {
  buildDialogueSnapshotKey,
  shouldLoadDialogueSnapshot,
} from '@/lib/dialogue/sessionRecovery';
import { isPatientTaskReadOnly } from '@/lib/patient/taskGroups';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { createDialogueSsePath } from '@/lib/transports/sseClient';
import { applyRealtimeEvent } from '@/lib/transports/applyRealtimeEvent';
import {
  toDomainSseEnvelope,
  toHandoffSseEnvelope,
} from '@/lib/transports/handoffResponse';
import {
  VoiceSocketClient,
  type VoiceConnectionState,
} from '@/lib/transports/voiceSocket';
import type {
  CicareStage,
  InteractionEvent,
  InteractionMessage,
  InteractionSession,
  StructuredAnswer,
} from '@/lib/types';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PencilSquareIcon,
  PauseIcon,
  PlayIcon,
  SpeakerXMarkIcon,
  SparklesIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';

interface ScriptResult {
  stage: CicareStage;
  content: string;
  answer?: StructuredAnswer;
  education?: {
    title: string;
    content: string;
    priority: InteractionEvent['priority'];
  };
  complete?: boolean;
}

const totalQuestions = 7;

function buildScriptResult(answerIndex: number, content: string): ScriptResult {
  const normalized = content.trim();
  if (answerIndex === 0) {
    return {
      stage: 'introduce',
      content: '谢谢您的配合。我是AI护理评估助手，本次回答会由护士复核。首先请告诉我您的年龄。',
      answer: {
        questionId: 'ready',
        questionCode: 'READY',
        questionText: '是否准备开始评估',
        answerText: normalized,
        sourceMessageIds: [],
        extractionConfidence: 0.99,
        corrected: false,
      },
    };
  }
  if (answerIndex === 1) {
    const age = Number.parseInt(normalized, 10);
    return {
      stage: 'communicate',
      content: '已记录。请问您是否对药物或食物过敏？如果有，请告诉我具体名称和发生过的反应。',
      answer: {
        questionId: 'age',
        questionCode: 'AGE',
        questionText: '年龄',
        answerNumber: Number.isNaN(age) ? undefined : age,
        answerText: Number.isNaN(age) ? normalized : undefined,
        sourceMessageIds: [],
        extractionConfidence: Number.isNaN(age) ? 0.72 : 0.98,
        corrected: false,
      },
    };
  }
  if (answerIndex === 2) {
    const hasAllergy = /有|过敏|青霉素|头孢|食物/.test(normalized);
    return {
      stage: 'ask',
      content: hasAllergy
        ? '我已记录您的过敏信息。如曾出现呼吸困难、喉头发紧、意识不清或需要急救，请立即告诉护士。接下来请问您下床或行走时是否需要他人搀扶或陪同？'
        : '好的，已记录目前没有明确过敏史。请问您下床或行走时是否需要他人搀扶或陪同？',
      answer: {
        questionId: 'allergy',
        questionCode: 'ALLERGY',
        questionText: '药物或食物过敏史',
        answerText: normalized,
        sourceMessageIds: [],
        extractionConfidence: 0.95,
        corrected: false,
      },
      education: hasAllergy
        ? {
            title: '过敏安全提醒',
            content: '以后每次就医、检查和用药前，请主动告诉医生和护士您的具体过敏物及过敏表现。',
            priority: 'high',
          }
        : undefined,
    };
  }
  if (answerIndex === 3) {
    return {
      stage: 'ask',
      content: '请问您最近一年是否发生过跌倒或坠床？夜间起床时会不会头晕或站立不稳？',
      answer: {
        questionId: 'mobility',
        questionCode: 'MOBILITY',
        questionText: '下床或行走协助需求',
        answerText: normalized,
        sourceMessageIds: [],
        extractionConfidence: 0.91,
        corrected: false,
      },
    };
  }
  if (answerIndex === 4) {
    const hasFallRisk = /有|跌|摔|头晕|不稳|需要/.test(normalized);
    return {
      stage: 'respond',
      content: '谢谢您说明。接下来想了解生活习惯：您目前是否吸烟？如果吸烟，大约每天多少支？',
      answer: {
        questionId: 'fall_history',
        questionCode: 'FALL_HISTORY',
        questionText: '跌倒史与夜间下床风险',
        answerText: normalized,
        sourceMessageIds: [],
        extractionConfidence: 0.94,
        corrected: false,
      },
      education: hasFallRisk
        ? {
            title: '防跌倒宣教',
            content: '夜间下床前请先按呼叫铃，穿防滑鞋，并等待护士或家属协助。',
            priority: 'high',
          }
        : undefined,
    };
  }
  if (answerIndex === 5) {
    const smokes = /吸|支|烟|抽/.test(normalized) && !/不吸|没有|戒/.test(normalized);
    return {
      stage: 'ask',
      content: '最后，请告诉我目前最主要的不舒服、担心，或者最希望护士帮助解决的问题。',
      answer: {
        questionId: 'smoking',
        questionCode: 'SMOKING',
        questionText: '吸烟情况',
        answerText: normalized,
        sourceMessageIds: [],
        extractionConfidence: 0.93,
        corrected: false,
      },
      education: smokes
        ? {
            title: '住院禁烟提醒',
            content: '病区为无烟环境。住院期间请不要在病房、卫生间或楼梯间吸烟，如有戒烟需求可告诉护士。',
            priority: 'medium',
          }
        : undefined,
    };
  }
  return {
    stage: 'exit',
    content: '感谢您的配合。本次评估问题已经完成，我已整理您的回答并提交给护士复核。接下来请完成知情同意确认。',
    answer: {
      questionId: 'symptoms',
      questionCode: 'SYMPTOMS',
      questionText: '主要不适、担心与帮助需求',
      answerText: normalized,
      sourceMessageIds: [],
      extractionConfidence: 0.9,
      corrected: false,
    },
    complete: true,
  };
}

export default function PatientDialoguePage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const voiceClientRef = useRef<VoiceSocketClient | undefined>(undefined);
  const loadedSnapshotKeyRef = useRef<string | null>(null);
  const handoffSubmittingRef = useRef(false);
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const readOnly = isPatientTaskReadOnly(task);
  const updateTask = useTaskStore((state) => state.updateTask);
  const session = useChatStore((state) => state.sessions[taskId]);
  const structuredAnswers = useChatStore((state) => state.structuredAnswers);
  const interactionEvents = useChatStore((state) => state.events);
  const educationCards = useChatStore((state) => state.educationCards);
  const consentRequests = useChatStore((state) => state.consentRequests);
  const answers = structuredAnswers[taskId] ?? [];
  const historyTimeline = useMemo(
    () =>
      buildDialogueHistoryTimeline({
        messages: session?.messages,
        educationCards: educationCards[taskId],
        consentRequests: consentRequests[taskId],
        events: interactionEvents[taskId],
      }),
    [
      consentRequests,
      educationCards,
      interactionEvents,
      session?.messages,
      taskId,
    ]
  );
  const streamingTaskId = useChatStore((state) => state.streamingTaskId);
  const setSession = useChatStore((state) => state.setSession);
  const addMessage = useChatStore((state) => state.addMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const upsertAnswer = useChatStore((state) => state.upsertStructuredAnswer);
  const addEvent = useChatStore((state) => state.addEvent);
  const updateConsentRequest = useChatStore(
    (state) => state.updateConsentRequest
  );
  const saveConsent = useTaskStore((state) => state.saveConsent);
  const setStreaming = useChatStore((state) => state.setStreaming);
  const [isRecording, setIsRecording] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isHandoffSubmitting, setIsHandoffSubmitting] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [voiceState, setVoiceState] =
    useState<VoiceConnectionState>('idle');
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text');
  const [voiceCompletionReadyTaskId, setVoiceCompletionReadyTaskId] =
    useState<string | null>(null);
  const [editingAnswerId, setEditingAnswerId] = useState<string | null>(null);
  const [correction, setCorrection] = useState('');

  const dialogueSnapshotKey = task
    ? buildDialogueSnapshotKey(taskId, task.sessionId)
    : '';

  useEffect(() => {
    const currentTask = useTaskStore
      .getState()
      .tasks.find((item) => item.id === taskId);
    const hasSession = Boolean(
      useChatStore.getState().sessions[taskId]
    );
    if (
      !shouldLoadDialogueSnapshot({
        dataMode: runtimeConfig.dataMode,
        hasTask: Boolean(currentTask),
        hasSession,
        snapshotKey: dialogueSnapshotKey,
        loadedSnapshotKey: loadedSnapshotKeyRef.current,
      }) ||
      !currentTask
    ) {
      return;
    }

    if (runtimeConfig.dataMode === 'mock') {
      const timestamp = Date.now();
      const sessionId =
        currentTask.sessionId ?? `SESSION-${taskId}-${timestamp}`;
      const welcome: InteractionMessage = {
        id: `MSG-${timestamp}`,
        messageNo: `MSG-${timestamp}`,
        sessionId,
        turnNo: 1,
        role: 'ai',
        cicareStage: 'connect',
        intentType: 'greeting',
        contentText: `您好，${currentTask.participantName ?? currentTask.patientName}。我是AI护理评估助手小医，请确认您现在方便开始评估吗？`,
        occurredAt: new Date().toISOString(),
      };
      const nextSession: InteractionSession = {
        id: sessionId,
        sessionNo: sessionId,
        taskId,
        patientId: currentTask.patientId,
        encounterId: currentTask.encounterId,
        interactionType: 'assessment',
        channelType: 'mixed',
        sessionStatus: 'active',
        startedAt: new Date().toISOString(),
        currentCicareStage: 'connect',
        answeredQuestionCount: 0,
        totalQuestionCount: totalQuestions,
        messages: [welcome],
      };
      setSession(taskId, nextSession);
      updateTask(taskId, {
        sessionId,
        ...(readOnly
          ? {}
          : {
              taskStatus: 'in_progress' as const,
              currentStage: 'connect' as const,
              progress: { current: 0, total: totalQuestions },
            }),
      });
      return;
    }

    loadedSnapshotKeyRef.current = dialogueSnapshotKey;
    // API 快照是当前任务领域事件的事实来源，先移除 sessionStorage 中
    // 可能残留的旧卡片，避免提交已经不存在的领域事件 ID。
    useChatStore.getState().clearTaskDomainState(taskId);
    const controller = new AbortController();
    void careRepository
      .getDialogueSnapshot(currentTask, controller.signal)
      .then((snapshot) => {
        loadedSnapshotKeyRef.current = buildDialogueSnapshotKey(
          taskId,
          snapshot.session.id
        );
        setSession(taskId, snapshot.session);
        useChatStore
          .getState()
          .setStructuredAnswers(taskId, snapshot.answers);
        snapshot.events.forEach(applyRealtimeEvent);
        setConnectionError('');
        updateTask(taskId, {
          sessionId: snapshot.session.id,
          ...(readOnly
            ? {}
            : {
                taskStatus: 'in_progress' as const,
                currentStage: snapshot.session.currentCicareStage,
                progress: {
                  current: snapshot.session.answeredQuestionCount ?? 0,
                  total:
                    snapshot.session.totalQuestionCount ??
                    currentTask.progress?.total ??
                    totalQuestions,
                },
              }),
        });
      })
      .catch((loadError) => {
        if (controller.signal.aborted || isRequestCancelled(loadError)) return;
        loadedSnapshotKeyRef.current = null;
        setConnectionError(
          loadError instanceof Error
            ? `会话加载失败：${loadError.message}`
            : '会话加载失败'
        );
      });
    return () => abortRequest(controller);
  }, [
    dialogueSnapshotKey,
    readOnly,
    setSession,
    taskId,
    updateTask,
  ]);

  const streamPath = session?.id
    ? createDialogueSsePath(session.id)
    : task?.sessionId
      ? createDialogueSsePath(task.sessionId)
      : undefined;
  const { status: streamStatus, error: streamError } = useRealtimeStream({
    path: streamPath,
    enabled: Boolean(task) && !readOnly,
  });

  useEffect(
    () => () => {
      void voiceClientRef.current?.close();
      voiceClientRef.current = undefined;
    },
    []
  );

  useEffect(() => {
    if (readOnly) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [readOnly, session?.messages.length]);

  const patientAnswerCount = useMemo(
    () => session?.messages.filter((message) => message.role === 'patient').length ?? 0,
    [session?.messages]
  );
  const backendCompleted = session?.sessionStatus === 'completed';
  const completingVoice =
    backendCompleted &&
    runtimeConfig.dataMode === 'api' &&
    inputMode === 'voice' &&
    voiceCompletionReadyTaskId !== taskId;
  const completed = backendCompleted && !completingVoice;
  const preparing = session?.sessionStatus === 'pending';
  const awaitingReply =
    !readOnly &&
    !completed &&
    session?.messages.at(-1)?.role === 'patient' &&
    runtimeConfig.dataMode === 'api';
  const isStreaming =
    !readOnly &&
    (preparing || streamingTaskId === taskId || isSending || awaitingReply);
  const displayedTotalQuestions =
    runtimeConfig.dataMode === 'api'
      ? session?.totalQuestionCount ?? task?.progress?.total ?? totalQuestions
      : totalQuestions;

  useEffect(() => {
    if (
      !backendCompleted ||
      runtimeConfig.dataMode !== 'api' ||
      inputMode !== 'voice'
    ) {
      return;
    }
    let active = true;
    void (async () => {
      try {
        await voiceClientRef.current?.finishAndCloseAfterPlayback();
      } finally {
        if (!active) return;
        voiceClientRef.current = undefined;
        setIsRecording(false);
        setVoiceState('closed');
        setVoiceCompletionReadyTaskId(taskId);
      }
    })();
    return () => {
      active = false;
    };
  }, [backendCompleted, inputMode, taskId]);

  const streamAssistantMessage = async (result: ScriptResult) => {
    if (!session) return;
    const messageId = `MSG-${Date.now()}-AI`;
    const message: InteractionMessage = {
      id: messageId,
      messageNo: messageId,
      sessionId: session.id,
      turnNo: session.messages.length + 2,
      role: 'ai',
      cicareStage: result.stage,
      intentType: result.complete ? 'confirmation' : 'question',
      contentText: '',
      occurredAt: new Date().toISOString(),
      isStreaming: true,
    };
    addMessage(taskId, message);
    setStreaming(taskId);
    const chunks = result.content.match(/.{1,6}/g) ?? [result.content];
    let currentText = '';
    for (const chunk of chunks) {
      currentText += chunk;
      updateMessage(taskId, messageId, { contentText: currentText });
      await new Promise((resolve) => setTimeout(resolve, 45));
    }
    updateMessage(taskId, messageId, { isStreaming: false });
    setStreaming(null);
  };

  const handleSendMessage = async (content: string) => {
    const currentSession = useChatStore.getState().sessions[taskId];
    if (!currentSession || readOnly || isPaused || isStreaming || completed) return;
    const messageId = `MSG-${Date.now()}-PATIENT`;
    const patientMessage: InteractionMessage = {
      id: messageId,
      messageNo: messageId,
      sessionId: currentSession.id,
      turnNo: currentSession.messages.length + 1,
      role: 'patient',
      cicareStage: currentSession.currentCicareStage,
      intentType: 'answer',
      contentText: content,
      occurredAt: new Date().toISOString(),
    };
    addMessage(taskId, patientMessage);

    if (runtimeConfig.dataMode === 'api') {
      setIsSending(true);
      setConnectionError('');
      try {
        await careRepository.sendDialogMessage({
          taskId,
          sessionId: currentSession.id,
          content,
          clientMessageId: messageId,
          inputMode: 'text',
        });
      } catch (sendError) {
        setConnectionError(
          sendError instanceof Error
            ? `发送失败：${sendError.message}`
            : '消息发送失败'
        );
      } finally {
        setIsSending(false);
      }
      return;
    }

    const result = buildScriptResult(patientAnswerCount, content);
    if (result.answer) {
      upsertAnswer(taskId, {
        ...result.answer,
        sourceMessageIds: [messageId],
      });
    }
    if (result.education) {
      const event: InteractionEvent = {
        id: `EVENT-${Date.now()}`,
        taskId,
        messageId,
        eventType: 'education',
        title: result.education.title,
        description: result.education.content,
        priority: result.education.priority,
        handled: false,
        occurredAt: new Date().toISOString(),
      };
      addEvent(taskId, event);
    }

    await streamAssistantMessage(result);
    const latestSession = useChatStore.getState().sessions[taskId];
    if (!latestSession) return;
    const answered = Math.min(patientAnswerCount + 1, totalQuestions);
    const summary = result.complete
      ? '患者已完成入院评估，系统记录了年龄、过敏史、活动能力、跌倒风险、吸烟情况以及主要不适，需护士复核。'
      : latestSession.aiSummary;
    setSession(taskId, {
      ...latestSession,
      currentCicareStage: result.stage,
      answeredQuestionCount: answered,
      sessionStatus: result.complete ? 'completed' : 'active',
      completedAt: result.complete ? new Date().toISOString() : undefined,
      aiSummary: summary,
    });
    updateTask(taskId, {
      currentStage: result.stage,
      progress: { current: answered, total: totalQuestions },
      taskStatus:
        result.complete && !task?.consentRequired ? 'pending_review' : 'in_progress',
      aiSummary: summary,
    });
  };

  const requestPatientHandoff = async (
    reason: string,
    requestedAction = 'other'
  ) => {
    if (handoffSubmittingRef.current) return null;
    handoffSubmittingRef.current = true;
    setIsHandoffSubmitting(true);
    try {
      return await careRepository.requestHandoff(taskId, reason, {
        requestedAction,
        clientInvocationId: createClientInvocationId('patient-handoff'),
      });
    } finally {
      handoffSubmittingRef.current = false;
      setIsHandoffSubmitting(false);
    }
  };

  const askNurse = async () => {
    const reason = '患者在AI对话评估中主动请求护士协助';
    try {
      const response = await requestPatientHandoff(reason);
      if (!response) return;
      applyRealtimeEvent(
        toHandoffSseEnvelope(response, {
          taskId,
          sessionId: session?.id,
          eventType: 'handoff_requested',
        })
      );
      setConnectionError('');
    } catch (handoffError) {
      setConnectionError(
        handoffError instanceof Error
          ? `呼叫护士失败：${handoffError.message}`
          : '呼叫护士失败'
      );
      return;
    }
  };

  const handleConsentSubmit = async (
    progress: Parameters<typeof saveConsent>[0]
  ) => {
    if (progress.decision === 'needs_explanation') {
      const reason = '患者对知情同意内容需要护士人工解释';
      const response = await requestPatientHandoff(reason, 'explain_consent');
      if (response) {
        applyRealtimeEvent(
          toHandoffSseEnvelope(response, {
            taskId,
            sessionId: session?.id,
            eventType: 'handoff_requested',
          })
        );
      }
    }
    await careRepository.submitConsent(progress);
    saveConsent(progress);
    if (progress.formId) {
      updateConsentRequest(taskId, progress.formId, {
        status:
          progress.decision === 'agreed'
            ? 'signed'
            : progress.decision === 'needs_explanation'
              ? 'needs_explanation'
              : 'refused',
        decision: progress.decision,
        clauses: progress.clauses,
        completedAt: progress.completedAt,
      });
    }
    if (progress.decision === 'agreed') {
      updateTask(taskId, { taskStatus: 'pending_review' });
    }
  };

  const handleEducationAcknowledge = async (
    eventId: string,
    materialId: string
  ) => {
    try {
      const response = await careRepository.acknowledgeEducation(
        taskId,
        eventId,
        materialId
      );
      applyRealtimeEvent(
        toDomainSseEnvelope(response, {
          taskId,
          sessionId: session?.id,
          eventType: 'education_status_updated',
        })
      );
      setConnectionError('');
    } catch (acknowledgeError) {
      setConnectionError(
        acknowledgeError instanceof Error
          ? `宣教确认失败：${acknowledgeError.message}`
          : '宣教确认失败'
      );
      throw acknowledgeError;
    }
  };

  const togglePause = async () => {
    const current = useChatStore.getState().sessions[taskId];
    if (!current) return;
    const nextPaused = !isPaused;
    try {
      if (nextPaused) {
        await careRepository.pauseDialogue(current.id);
        await voiceClientRef.current?.pause();
      } else {
        await careRepository.resumeDialogue(current.id);
        await voiceClientRef.current?.resume();
      }
      setIsPaused(nextPaused);
      setSession(taskId, {
        ...current,
        sessionStatus: nextPaused ? 'paused' : 'active',
      });
    } catch (pauseError) {
      setConnectionError(
        pauseError instanceof Error
          ? pauseError.message
          : '会话状态更新失败'
      );
    }
  };

  const startVoice = async () => {
    if (runtimeConfig.dataMode === 'mock') {
      setIsRecording(true);
      setVoiceState('listening');
      return;
    }
    const currentSession = useChatStore.getState().sessions[taskId];
    if (!currentSession) {
      setConnectionError('会话尚未准备完成，请稍后重试');
      return;
    }
    if (
      voiceClientRef.current &&
      voiceState === 'paused'
    ) {
      await voiceClientRef.current.resume();
      return;
    }
    await voiceClientRef.current?.close();
    const client = new VoiceSocketClient({
      taskId,
      sessionId: currentSession.id,
      onStateChange: (state) => {
        setVoiceState(state);
        setIsRecording(
          state === 'listening' ||
            state === 'transcribing' ||
            state === 'thinking' ||
            state === 'speaking'
        );
      },
      onError: setConnectionError,
    });
    voiceClientRef.current = client;
    try {
      await client.start();
    } catch {
      setIsRecording(false);
      setVoiceState('text_fallback');
    }
  };

  const changeInputMode = async (mode: 'text' | 'voice') => {
    if (mode === inputMode) return;
    if (mode === 'text') {
      await voiceClientRef.current?.close();
      voiceClientRef.current = undefined;
      setIsRecording(false);
      setVoiceState('idle');
    }
    setConnectionError('');
    setInputMode(mode);
  };

  const closeVoice = async () => {
    try {
      await voiceClientRef.current?.close();
    } finally {
      voiceClientRef.current = undefined;
      setIsRecording(false);
      setVoiceState('closed');
      setInputMode('text');
    }
  };

  const stopVoice = async () => {
    setIsRecording(false);
    if (runtimeConfig.dataMode === 'mock') {
      setVoiceState('transcribing');
      await handleSendMessage('我通过语音回答：目前情况还可以');
      setVoiceState('idle');
      return;
    }
    try {
      await voiceClientRef.current?.pause();
    } catch (voiceError) {
      setVoiceState('text_fallback');
      setConnectionError(
        voiceError instanceof Error
          ? voiceError.message
          : '语音暂停失败，已切换文字输入'
      );
    }
  };

  const saveCorrection = () => {
    const answer = answers.find((item) => item.questionId === editingAnswerId);
    if (!answer || !correction.trim()) return;
    upsertAnswer(taskId, {
      ...answer,
      answerText: correction.trim(),
      answerNumber: undefined,
      corrected: true,
    });
    setEditingAnswerId(null);
    setCorrection('');
  };

  if (!task) {
    return (
      <PatientLayout title="AI对话评估" showBack>
        <div className="p-6 text-center">任务不存在</div>
      </PatientLayout>
    );
  }

  return (
    <PatientLayout title="AI智能评估" showBack onBack={() => router.push(`/patient/tasks/${taskId}`)}>
      <div className="h-[calc(100vh-3.5rem)] flex flex-col">
        <div className="bg-surface border-b border-border p-3">
          <div className="max-w-6xl mx-auto flex items-center gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 text-sm font-medium">
                <SparklesIcon className="w-5 h-5 text-primary" />
                {readOnly
                  ? '历史对话记录'
                  : completed
                    ? '评估已完成'
                    : completingVoice
                      ? '正在完成最后一条回复'
                    : isPaused
                    ? '评估已暂停'
                    : isStreaming
                      ? 'AI正在生成回复'
                      : '评估进行中'}
              </div>
              <Progress
                value={session?.answeredQuestionCount ?? 0}
                max={displayedTotalQuestions}
                size="sm"
                className="mt-2"
              />
            </div>
            {readOnly ? (
              <Badge variant="default" size="sm">只读</Badge>
            ) : (
              <IntegrationStatus
                streamStatus={streamStatus}
                voiceState={
                  inputMode === 'voice' ? voiceState : undefined
                }
              />
            )}
            <Badge variant={isStreaming ? 'info' : 'primary'} size="sm">
              {session?.answeredQuestionCount ?? 0}/{displayedTotalQuestions}
            </Badge>
            {runtimeConfig.dataMode === 'mock' && !readOnly && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void togglePause()}
              >
                {isPaused ? <PlayIcon className="w-4 h-4 mr-1" /> : <PauseIcon className="w-4 h-4 mr-1" />}
                {isPaused ? '继续' : '暂停'}
              </Button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-hidden">
          <div className="max-w-6xl mx-auto h-full grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="scrollbar-soft overflow-y-auto p-4">
              {historyTimeline.map((item) => {
                if (item.kind === 'message') {
                  return (
                    <ChatBubble
                      key={item.id}
                      message={item.message}
                      showAvatar
                      animate
                    />
                  );
                }
                if (item.kind === 'education') {
                  return (
                    <EducationMaterialCard
                      key={item.id}
                      card={item.item}
                      readOnly={readOnly}
                      onAcknowledge={() =>
                        handleEducationAcknowledge(
                          item.item.id,
                          item.item.materialId
                        )
                      }
                    />
                  );
                }
                if (item.kind === 'consent') {
                  return (
                    <ConsentInteractionCard
                      key={item.id}
                      request={item.item}
                      participantName={task.participantName ?? task.patientName}
                      readOnly={readOnly}
                      onSubmit={handleConsentSubmit}
                    />
                  );
                }
                if (item.event.eventType === 'handoff') {
                  return (
                    <div key={item.id} className="mb-4">
                      <HandoffHistoryCard event={item.event} />
                    </div>
                  );
                }
                return (
                  <div
                    key={item.id}
                    className={`rounded-2xl border p-4 mb-4 ${
                      item.event.priority === 'high'
                        ? 'bg-red-50 border-red-200'
                        : 'bg-amber-50 border-amber-200'
                    }`}
                  >
                    <div className="flex items-center gap-2 font-medium">
                      <ExclamationTriangleIcon className="w-5 h-5" />
                      {item.event.title}
                    </div>
                    <p className="text-sm mt-1">{item.event.description}</p>
                    {readOnly ? (
                      <p className="mt-2 text-xs text-foreground-muted">
                        {item.event.handled ? '患者已了解' : '历史风险记录'}
                      </p>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          useChatStore
                            .getState()
                            .markEventHandled(taskId, item.event.id)
                        }
                        className="mt-2 text-xs text-primary underline"
                      >
                        {item.event.handled ? '已了解' : '我已了解'}
                      </button>
                    )}
                  </div>
                );
              })}
              {answers.length > 0 && (
                <details className="lg:hidden rounded-2xl border border-border bg-surface p-4 mb-4">
                  <summary className="font-medium cursor-pointer">查看已记录信息（{answers.length}项）</summary>
                  <div className="mt-3 space-y-3">
                    {answers.map((answer) => (
                      <div key={answer.questionId} className="rounded-xl bg-surface-secondary p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-xs text-foreground-muted">{answer.questionText}</p>
                            <p className="text-sm font-medium mt-1">
                              {getStructuredAnswerDisplayValue(answer)}
                            </p>
                          </div>
                          {!readOnly && (
                            <button
                              type="button"
                              onClick={() => {
                                setEditingAnswerId(answer.questionId);
                                setCorrection(getStructuredAnswerDisplayValue(answer));
                              }}
                              className="text-primary"
                              aria-label={`纠正${answer.questionText}`}
                            >
                              <PencilSquareIcon className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                    {!readOnly && editingAnswerId && (
                      <div className="rounded-xl bg-primary-tint p-3">
                        <textarea
                          value={correction}
                          onChange={(event) => setCorrection(event.target.value)}
                          className="w-full rounded-xl border border-border bg-surface p-3 text-sm"
                          rows={2}
                        />
                        <Button size="sm" className="mt-2 w-full" onClick={saveCorrection}>
                          保存更正
                        </Button>
                      </div>
                    )}
                  </div>
                </details>
              )}
              <div ref={messagesEndRef} />
            </div>

            <aside className="scrollbar-soft hidden overflow-y-auto border-l border-border bg-surface-secondary p-4 lg:block">
              <h2 className="text-lg font-sans font-semibold mb-1">已记录信息</h2>
              <p className="text-xs text-foreground-muted mb-4">
                {readOnly
                  ? '以下为本次评估已记录的信息，仅供查看。'
                  : '以下内容仍需护士确认，您可以随时纠正。'}
              </p>
              <div className="space-y-3">
                {answers.length === 0 ? (
                  <p className="text-sm text-foreground-muted">回答后将在此显示结构化信息。</p>
                ) : (
                  answers.map((answer) => (
                    <Card key={answer.questionId} padding="sm">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs text-foreground-muted">{answer.questionText}</p>
                          <p className="text-sm font-medium mt-1">
                            {getStructuredAnswerDisplayValue(answer)}
                          </p>
                          <p className="text-xs text-foreground-muted mt-1">
                            可信度 {Math.round(answer.extractionConfidence * 100)}%
                            {answer.corrected && ' · 已更正'}
                          </p>
                        </div>
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => {
                              setEditingAnswerId(answer.questionId);
                              setCorrection(getStructuredAnswerDisplayValue(answer));
                            }}
                            className="text-primary"
                            aria-label={`纠正${answer.questionText}`}
                          >
                            <PencilSquareIcon className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </Card>
                  ))
                )}
              </div>
              {!readOnly && editingAnswerId && (
                <div className="mt-4 rounded-2xl border border-primary/20 bg-primary-tint p-4">
                  <label className="text-sm font-medium">纠正记录</label>
                  <textarea
                    value={correction}
                    onChange={(event) => setCorrection(event.target.value)}
                    className="w-full mt-2 rounded-xl border border-border bg-surface p-3 text-sm"
                    rows={3}
                  />
                  <div className="flex gap-2 mt-2">
                    <Button size="sm" variant="ghost" onClick={() => setEditingAnswerId(null)}>
                      取消
                    </Button>
                    <Button size="sm" onClick={saveCorrection}>保存更正</Button>
                  </div>
                </div>
              )}
            </aside>
          </div>
        </div>

        <div className="border-t border-border bg-surface">
          <div className="max-w-6xl mx-auto">
            {readOnly ? (
              <div className="flex items-center gap-3 p-4">
                <CheckCircleIcon className="h-6 w-6 text-primary" />
                <div className="flex-1">
                  <p className="font-medium">本次评估已提交，当前为只读查看</p>
                  <p className="text-xs text-foreground-muted">如需补充或修改，请联系责任护士。</p>
                </div>
                <Button
                  variant="outline"
                  onClick={() => router.push(`/patient/tasks/${taskId}`)}
                >
                  返回任务
                </Button>
              </div>
            ) : completed ? (
              <div className="p-4 flex items-center gap-3">
                <CheckCircleIcon className="w-6 h-6 text-success" />
                <div className="flex-1">
                  <p className="font-medium">AI评估已完成并提交护士复核</p>
                  <p className="text-xs text-foreground-muted">
                    {runtimeConfig.dataMode === 'api'
                      ? '您已完成本次评估，请等待护士复核'
                      : '下一步完成知情同意确认'}
                  </p>
                </div>
                <Button
                  onClick={() =>
                    router.push(task.consentRequired ? `/patient/consent/${taskId}` : `/patient/complete/${taskId}`)
                  }
                >
                  继续
                </Button>
              </div>
            ) : (
              <>
                <div className="px-4 pt-3 flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <p className="text-xs text-foreground-muted">
                      {isRecording
                        ? voiceState === 'speaking'
                          ? 'AI 正在播报，您可以直接说话打断'
                          : '实时语音已开启，系统会自动识别您的停顿'
                        : inputMode === 'voice'
                          ? '语音模式：点击麦克风开启连续实时对话'
                          : '文字模式：输入并发送您的回答'}
                    </p>
                    {completingVoice && (
                      <p className="shrink-0 text-xs text-primary">
                        正在等待最后一段语音播报完成……
                      </p>
                    )}
                    <div
                      className="flex shrink-0 rounded-lg border border-border p-0.5"
                      role="group"
                      aria-label="对话输入模式"
                    >
                      {(['text', 'voice'] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => void changeInputMode(mode)}
                          disabled={isRecording || isStreaming || completingVoice}
                          aria-pressed={inputMode === mode}
                          className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                            inputMode === mode
                              ? 'bg-primary text-white'
                              : 'text-foreground-muted hover:bg-surface-secondary'
                          }`}
                        >
                          {mode === 'text' ? '文字' : '语音'}
                        </button>
                      ))}
                    </div>
                    {inputMode === 'voice' &&
                      voiceState !== 'idle' &&
                      voiceState !== 'closed' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void closeVoice()}
                          disabled={completingVoice}
                          className="shrink-0 text-danger"
                          title="关闭实时语音并保留文字输入"
                        >
                          <SpeakerXMarkIcon className="mr-1 h-4 w-4" />
                          关闭语音
                        </Button>
                      )}
                  </div>
                  <button
                    type="button"
                    onClick={() => void askNurse()}
                    disabled={isHandoffSubmitting}
                    className="text-sm text-danger flex items-center gap-1 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <UserPlusIcon className="w-4 h-4" />
                    {isHandoffSubmitting ? '正在呼叫' : '找护士'}
                  </button>
                </div>
                <ChatInput
                  onSend={handleSendMessage}
                  onVoiceStart={
                    inputMode === 'voice' ? () => void startVoice() : undefined
                  }
                  onVoiceStop={
                    inputMode === 'voice' ? () => void stopVoice() : undefined
                  }
                  placeholder={
                    isPaused
                      ? '评估已暂停'
                      : inputMode === 'voice'
                        ? '语音模式下请点击麦克风回答'
                        : '输入您的回答...'
                  }
                  disabled={
                    isPaused ||
                    completingVoice ||
                    (inputMode === 'text' && isStreaming)
                  }
                  isRecording={isRecording}
                  recordingLabel="实时语音已开启，停顿后系统会自动回复"
                />
              </>
            )}
            {(connectionError || streamError) && (
              <div
                role="alert"
                className="mx-4 mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800"
              >
                {connectionError || streamError}
                {voiceState === 'text_fallback' && '，您仍可继续使用文字输入。'}
              </div>
            )}
          </div>
        </div>
      </div>
    </PatientLayout>
  );
}
