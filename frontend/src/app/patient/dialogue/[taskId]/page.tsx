'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import ConsentInteractionCard from '@/components/chat/ConsentInteractionCard';
import EducationMaterialCard from '@/components/chat/EducationMaterialCard';
import HandoffHistoryCard from '@/components/chat/HandoffHistoryCard';
import { PatientChatBubble } from '@/components/patient/PatientChatBubble';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { VoiceOrb } from '@/components/patient/VoiceOrb';
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
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('voice');
  const [voiceCompletionReadyTaskId, setVoiceCompletionReadyTaskId] =
    useState<string | null>(null);
  const [editingAnswerId, setEditingAnswerId] = useState<string | null>(null);
  const [correction, setCorrection] = useState('');
  const [manualInterventionReason, setManualInterventionReason] = useState('');
  const [messageDraft, setMessageDraft] = useState('');
  const [pendingVoiceTranscript, setPendingVoiceTranscript] = useState('');

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
        setManualInterventionReason(
          snapshot.manualIntervention
            ? snapshot.interventionReason ?? '部分字段需要医护人工确认'
            : ''
        );
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
    setPendingVoiceTranscript('');
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
      setPendingVoiceTranscript('我目前感觉还可以，没有特别不舒服。');
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

  const confirmVoiceTranscript = async () => {
    const transcript = pendingVoiceTranscript.trim();
    if (!transcript) return;
    setPendingVoiceTranscript('');
    setVoiceState('thinking');
    await handleSendMessage(transcript);
    setVoiceState('idle');
  };

  const interruptVoice = () => {
    voiceClientRef.current?.interrupt();
    setVoiceState('listening');
    setIsRecording(true);
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
  const visualVoiceState: VoiceConnectionState = connectionError
    ? 'text_fallback'
    : isPaused
      ? 'paused'
      : inputMode === 'voice' &&
          isStreaming &&
          (voiceState === 'idle' || voiceState === 'closed')
        ? 'thinking'
        : voiceState;
  const progressValue = session?.answeredQuestionCount ?? 0;
  const progressPercentage = Math.round(
    (progressValue / Math.max(displayedTotalQuestions, 1)) * 100
  );

  if (!task) {
    return (
      <PatientLayout title="AI对话评估" showBack>
        <div className="p-6 text-center">
          <Image
            src="/assets/patient/states/empty-tasks.svg"
            alt=""
            width={96}
            height={96}
            priority
            className="mx-auto h-24 w-24"
          />
          <p className="mt-4 font-bold">任务不存在或已经失效</p>
        </div>
      </PatientLayout>
    );
  }

  return (
    <PatientLayout
      title="AI智能评估"
      showBack
      onBack={() => router.push(`/patient/tasks/${taskId}`)}
      headerRight={
        <button
          type="button"
          onClick={() => void askNurse()}
          disabled={isHandoffSubmitting}
          className="patient-touch-button min-w-[78px] gap-1 rounded-full bg-primary px-3 text-white disabled:opacity-50"
          aria-label={isHandoffSubmitting ? '正在呼叫护士' : '找护士'}
        >
          <PatientIcon name="nurse" className="h-5 w-5" />
          <span className="text-sm font-bold">找护士</span>
        </button>
      }
    >
      <div className="flex h-[calc(100dvh-64px)] flex-col overflow-hidden">
        <section className="shrink-0 border-b border-border bg-[#fffaf6]/90 px-[18px] py-3">
          <div className="flex items-center gap-3">
            <span className="font-black text-primary">{progressValue}</span>
            <span className="-ml-2 text-sm text-foreground-muted">
              / {displayedTotalQuestions}
            </span>
            <div className="patient-progress-track flex-1">
              <div
                className="patient-progress-value"
                style={{ width: `${progressPercentage}%` }}
              />
            </div>
            {readOnly ? (
              <span className="rounded-full bg-[#eee9e3] px-2.5 py-1 text-xs font-bold text-foreground-muted">
                只读
              </span>
            ) : (
              <IntegrationStatus
                compact
                streamStatus={streamStatus}
                voiceState={inputMode === 'voice' ? voiceState : undefined}
              />
            )}
          </div>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-xs text-foreground-muted">
            <PatientIcon name="lock" className="h-4 w-4" />
            仅在您点击后使用麦克风
          </p>
        </section>

        <div className="scrollbar-soft flex-1 overflow-y-auto px-[14px] py-4">
          {inputMode === 'voice' && !readOnly && !completed && (
            <section className="pb-4 pt-2">
              <VoiceOrb state={visualVoiceState} />
              {(voiceState === 'listening' || isRecording) && (
                <button
                  type="button"
                  onClick={() => void stopVoice()}
                  className="patient-outline-button mx-auto mt-4 flex min-w-[160px] rounded-full"
                >
                  结束回答
                </button>
              )}
            </section>
          )}

          <section
            className={`${
              inputMode === 'voice' && !readOnly
                ? 'patient-card rounded-[26px] p-3'
                : ''
            }`}
            aria-label="评估对话记录"
          >
            {historyTimeline.map((item) => {
              if (item.kind === 'message') {
                return (
                  <PatientChatBubble key={item.id} message={item.message} />
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
                  className={`mb-4 rounded-2xl border p-4 ${
                    item.event.priority === 'high'
                      ? 'border-red-200 bg-red-50'
                      : 'border-amber-200 bg-amber-50'
                  }`}
                >
                  <div className="flex items-center gap-2 font-bold">
                    <PatientIcon name="warning" className="h-5 w-5" />
                    {item.event.title}
                  </div>
                  <p className="mt-1 text-sm leading-6">
                    {item.event.description}
                  </p>
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
                      className="mt-2 text-xs font-bold text-primary underline"
                    >
                      {item.event.handled ? '已了解' : '我已了解'}
                    </button>
                  )}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </section>

          {pendingVoiceTranscript || voiceState === 'transcribing' ? (
            <section className="patient-card mt-3 p-3">
              <div className="flex items-center gap-2 rounded-2xl bg-[#edf8f7] px-3 py-3 font-bold text-[#258f91]">
                <PatientIcon name="microphone" className="h-5 w-5" />
                <span className="flex-1">
                  {pendingVoiceTranscript || '正在等待后端返回可确认的转写内容…'}
                </span>
                {pendingVoiceTranscript && (
                  <PatientIcon name="check-circle" className="h-5 w-5" />
                )}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => void startVoice()}
                  className="patient-outline-button min-h-11 text-sm"
                >
                  <PatientIcon name="replay" className="h-5 w-5" />
                  重新说一遍
                </button>
                <button
                  type="button"
                  onClick={() => void confirmVoiceTranscript()}
                  disabled={!pendingVoiceTranscript}
                  className="patient-primary-button min-h-11 text-sm"
                >
                  <PatientIcon name="send" className="h-5 w-5" />
                  确认发送
                </button>
              </div>
            </section>
          ) : null}

          {answers.length > 0 && (
            <details className="patient-card mt-3 p-4">
              <summary className="cursor-pointer font-bold">
                查看已记录信息（{answers.length} 项）
              </summary>
              <div className="mt-3 space-y-2">
                {answers.map((answer) => (
                  <div
                    key={answer.questionId}
                    className="rounded-2xl bg-surface-secondary p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-xs text-foreground-muted">
                          {answer.questionText}
                        </p>
                        <p className="mt-1 text-sm font-bold">
                          {getStructuredAnswerDisplayValue(answer)}
                        </p>
                      </div>
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => {
                            setEditingAnswerId(answer.questionId);
                            setCorrection(
                              getStructuredAnswerDisplayValue(answer)
                            );
                          }}
                          className="patient-touch-button h-10 min-h-10 w-10 min-w-10 text-primary"
                          aria-label={`纠正${answer.questionText}`}
                        >
                          <PatientIcon name="edit" className="h-5 w-5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {!readOnly && editingAnswerId && (
                  <div className="rounded-2xl bg-primary-tint p-3">
                    <textarea
                      value={correction}
                      onChange={(event) => setCorrection(event.target.value)}
                      className="w-full rounded-xl border border-border bg-surface p-3 text-sm outline-none focus:border-primary"
                      rows={2}
                    />
                    <button
                      type="button"
                      className="patient-primary-button mt-2 min-h-11 w-full text-sm"
                      onClick={saveCorrection}
                    >
                      保存更正
                    </button>
                  </div>
                )}
              </div>
            </details>
          )}

          {(connectionError || streamError) && (
            <div
              role="alert"
              className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800"
            >
              {connectionError || streamError}
              {voiceState === 'text_fallback' && '，您仍可继续使用文字输入。'}
            </div>
          )}
          {manualInterventionReason && (
            <div
              role="status"
              className="mt-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
            >
              字段抽取需要医护人工处理：{manualInterventionReason}
              。对话仍可继续，人工填写结果将在后续请求中生效。
            </div>
          )}
        </div>

        <footer className="shrink-0 border-t border-border bg-[#fffaf6] px-[14px] pb-[max(10px,env(safe-area-inset-bottom))] pt-3 shadow-[0_-12px_28px_rgba(94,67,48,.08)]">
          {readOnly ? (
            <div className="flex items-center gap-3">
              <PatientIcon
                name="lock"
                className="h-7 w-7 text-foreground-muted"
              />
              <div className="min-w-0 flex-1">
                <p className="font-bold">本次评估已提交，当前为只读查看</p>
                <p className="text-xs text-foreground-muted">
                  如需补充或修改，请联系责任护士。
                </p>
              </div>
              <button
                type="button"
                className="patient-outline-button min-h-11 px-3 text-sm"
                onClick={() => router.push(`/patient/tasks/${taskId}`)}
              >
                返回
              </button>
            </div>
          ) : completed ? (
            <div className="flex items-center gap-3">
              <PatientIcon
                name="check-circle"
                className="h-7 w-7 text-success"
              />
              <div className="min-w-0 flex-1">
                <p className="font-bold">AI 评估已完成</p>
                <p className="text-xs text-foreground-muted">
                  {runtimeConfig.dataMode === 'api'
                    ? '结果已提交护士复核'
                    : '下一步完成知情同意确认'}
                </p>
              </div>
              <button
                type="button"
                className="patient-primary-button min-h-11 px-4 text-sm"
                onClick={() =>
                  router.push(
                    task.consentRequired
                      ? `/patient/consent/${taskId}`
                      : `/patient/complete/${taskId}`
                  )
                }
              >
                继续
              </button>
            </div>
          ) : inputMode === 'voice' ? (
            <>
              <div className="grid grid-cols-[1fr_92px_1fr] items-center gap-3">
                <button
                  type="button"
                  onClick={() => void changeInputMode('text')}
                  disabled={completingVoice}
                  className="flex min-h-[60px] flex-col items-center justify-center gap-1 text-xs font-bold text-foreground-muted disabled:opacity-50"
                >
                  <span className="patient-touch-button border border-border bg-white">
                    <PatientIcon name="keyboard" />
                  </span>
                  切换文字
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (voiceState === 'speaking') {
                      interruptVoice();
                    } else if (isRecording) {
                      void stopVoice();
                    } else {
                      void startVoice();
                    }
                  }}
                  disabled={
                    isPaused ||
                    completingVoice ||
                    voiceState === 'transcribing' ||
                    voiceState === 'thinking'
                  }
                  className="mx-auto grid h-20 w-20 place-items-center rounded-full border-[7px] border-white bg-gradient-to-br from-[#ff7557] to-[#ff5032] text-white shadow-[0_10px_26px_rgba(255,86,52,.28)] disabled:opacity-50"
                  aria-label={isRecording ? '结束回答' : '开始语音回答'}
                >
                  <PatientIcon
                    name={isRecording ? 'stop' : 'microphone'}
                    className="h-9 w-9"
                  />
                </button>
                <button
                  type="button"
                  onClick={interruptVoice}
                  disabled={voiceState !== 'speaking'}
                  className="flex min-h-[60px] flex-col items-center justify-center gap-1 text-xs font-bold text-foreground-muted disabled:opacity-45"
                >
                  <span className="patient-touch-button border border-border bg-white">
                    <PatientIcon name="interrupt" />
                  </span>
                  打断播报
                </button>
              </div>
              {voiceState !== 'idle' && voiceState !== 'closed' && (
                <button
                  type="button"
                  onClick={() => void closeVoice()}
                  disabled={completingVoice}
                  className="mx-auto mt-1 block text-xs font-bold text-danger underline disabled:opacity-50"
                >
                  关闭语音并保留文字输入
                </button>
              )}
              {completingVoice && (
                <p className="mt-2 text-center text-xs text-primary">
                  正在等待最后一段语音播报完成…
                </p>
              )}
            </>
          ) : (
            <div className="flex items-end gap-2">
              <button
                type="button"
                onClick={() => void changeInputMode('voice')}
                disabled={isStreaming || isPaused}
                className="patient-touch-button border border-border bg-white text-primary disabled:opacity-50"
                aria-label="切换语音"
              >
                <PatientIcon name="microphone" />
              </button>
              <textarea
                value={messageDraft}
                onChange={(event) => setMessageDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    const content = messageDraft.trim();
                    if (!content) return;
                    setMessageDraft('');
                    void handleSendMessage(content);
                  }
                }}
                placeholder={isPaused ? '评估已暂停' : '输入您的回答…'}
                disabled={isPaused || isStreaming || completingVoice}
                rows={1}
                className="min-h-12 max-h-28 min-w-0 flex-1 resize-none rounded-2xl border border-border bg-white px-4 py-3 text-sm outline-none focus:border-primary disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => {
                  const content = messageDraft.trim();
                  if (!content) return;
                  setMessageDraft('');
                  void handleSendMessage(content);
                }}
                disabled={
                  !messageDraft.trim() ||
                  isPaused ||
                  isStreaming ||
                  completingVoice
                }
                className="patient-touch-button bg-primary text-white disabled:opacity-40"
                aria-label="发送回答"
              >
                <PatientIcon name="send" />
              </button>
            </div>
          )}
          {runtimeConfig.dataMode === 'mock' && !readOnly && !completed && (
            <button
              type="button"
              onClick={() => void togglePause()}
              className="mx-auto mt-2 flex min-h-8 items-center gap-1 text-xs font-bold text-foreground-muted"
            >
              <PatientIcon
                name={isPaused ? 'play' : 'pause'}
                className="h-4 w-4"
              />
              {isPaused ? '继续评估' : '暂停评估'}
            </button>
          )}
        </footer>
      </div>
    </PatientLayout>
  );
}
