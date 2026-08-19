import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import {
  mockInteractionEvents,
  mockSessions,
  mockStructuredAnswers,
} from '@/lib/mock/dialogue';
import type {
  ConsentRequest,
  EducationCard,
  InteractionEvent,
  InteractionMessage,
  InteractionSession,
  MessageFeedback,
  NurseAssistanceRequest,
  StructuredAnswer,
} from '@/lib/types';

interface ChatStore {
  sessions: Record<string, InteractionSession>;
  structuredAnswers: Record<string, StructuredAnswer[]>;
  events: Record<string, InteractionEvent[]>;
  educationCards: Record<string, EducationCard[]>;
  consentRequests: Record<string, ConsentRequest[]>;
  nurseAssistanceRequests: Record<string, NurseAssistanceRequest>;
  feedback: Record<string, MessageFeedback>;
  streamingTaskId: string | null;
  setSession: (taskId: string, session: InteractionSession) => void;
  addMessage: (taskId: string, message: InteractionMessage) => void;
  upsertMessage: (taskId: string, message: InteractionMessage) => void;
  updateMessage: (
    taskId: string,
    messageId: string,
    updates: Partial<InteractionMessage>
  ) => void;
  setStructuredAnswers: (taskId: string, answers: StructuredAnswer[]) => void;
  upsertStructuredAnswer: (taskId: string, answer: StructuredAnswer) => void;
  addEvent: (taskId: string, event: InteractionEvent) => void;
  upsertEducationCard: (taskId: string, card: EducationCard) => void;
  updateEducationCard: (
    taskId: string,
    materialId: string,
    updates: Partial<EducationCard>
  ) => void;
  upsertConsentRequest: (taskId: string, request: ConsentRequest) => void;
  updateConsentRequest: (
    taskId: string,
    formId: string,
    updates: Partial<ConsentRequest>
  ) => void;
  upsertNurseAssistanceRequest: (request: NurseAssistanceRequest) => void;
  resolveNurseAssistanceRequest: (requestId: string) => void;
  markEventHandled: (taskId: string, eventId: string) => void;
  setFeedback: (taskId: string, feedback: MessageFeedback[]) => void;
  saveFeedback: (feedback: MessageFeedback) => void;
  setStreaming: (taskId: string | null) => void;
  clearSession: (taskId: string) => void;
  resetDemoData: () => void;
}

const initialState = {
  sessions: mockSessions,
  structuredAnswers: mockStructuredAnswers,
  events: mockInteractionEvents,
  educationCards: {},
  consentRequests: {},
  nurseAssistanceRequests: {},
  feedback: {},
  streamingTaskId: null,
};

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      ...initialState,

      setSession: (taskId, session) =>
        set((state) => ({
          sessions: { ...state.sessions, [taskId]: session },
        })),

      addMessage: (taskId, message) =>
        set((state) => {
          const session = state.sessions[taskId];
          if (!session) return state;
          return {
            sessions: {
              ...state.sessions,
              [taskId]: {
                ...session,
                messages: [...session.messages, message],
              },
            },
          };
        }),

      upsertMessage: (taskId, message) =>
        set((state) => {
          const session = state.sessions[taskId];
          if (!session) return state;
          const exists = session.messages.some((item) => item.id === message.id);
          return {
            sessions: {
              ...state.sessions,
              [taskId]: {
                ...session,
                messages: exists
                  ? session.messages.map((item) =>
                      item.id === message.id ? { ...item, ...message } : item
                    )
                  : [...session.messages, message],
              },
            },
          };
        }),

      updateMessage: (taskId, messageId, updates) =>
        set((state) => {
          const session = state.sessions[taskId];
          if (!session) return state;
          return {
            sessions: {
              ...state.sessions,
              [taskId]: {
                ...session,
                messages: session.messages.map((message) =>
                  message.id === messageId ? { ...message, ...updates } : message
                ),
              },
            },
          };
        }),

      setStructuredAnswers: (taskId, answers) =>
        set((state) => ({
          structuredAnswers: { ...state.structuredAnswers, [taskId]: answers },
        })),

      upsertStructuredAnswer: (taskId, answer) =>
        set((state) => {
          const current = state.structuredAnswers[taskId] ?? [];
          const exists = current.some((item) => item.questionId === answer.questionId);
          return {
            structuredAnswers: {
              ...state.structuredAnswers,
              [taskId]: exists
                ? current.map((item) =>
                    item.questionId === answer.questionId ? answer : item
                  )
                : [...current, answer],
            },
          };
        }),

      addEvent: (taskId, event) =>
        set((state) => ({
          events: {
            ...state.events,
            [taskId]: (state.events[taskId] ?? []).some(
              (item) => item.id === event.id
            )
              ? (state.events[taskId] ?? []).map((item) =>
                  item.id === event.id ? { ...item, ...event } : item
                )
              : [...(state.events[taskId] ?? []), event],
          },
        })),

      upsertEducationCard: (taskId, card) =>
        set((state) => {
          const current = state.educationCards[taskId] ?? [];
          const exists = current.some(
            (item) => item.materialId === card.materialId
          );
          return {
              educationCards: {
                ...state.educationCards,
                [taskId]: exists
                  ? current.map((item) =>
                    item.materialId === card.materialId
                      ? {
                          ...item,
                          ...card,
                          // SSE 重放同一材料时不能覆盖患者已经确认的状态。
                          acknowledged: item.acknowledged || card.acknowledged,
                        }
                      : item
                  )
                  : [...current, card],
            },
          };
        }),

      updateEducationCard: (taskId, materialId, updates) =>
        set((state) => ({
          educationCards: {
            ...state.educationCards,
            [taskId]: (state.educationCards[taskId] ?? []).map((item) =>
              item.materialId === materialId
                ? { ...item, ...updates }
                : item
            ),
          },
        })),

      upsertConsentRequest: (taskId, request) =>
        set((state) => {
          const current = state.consentRequests[taskId] ?? [];
          const exists = current.some(
            (item) => item.formId === request.formId
          );
          return {
              consentRequests: {
                ...state.consentRequests,
                [taskId]: exists
                  ? current.map((item) =>
                    item.formId === request.formId
                      ? {
                          ...item,
                          ...request,
                          // 页面刷新会先恢复数据库快照，再重放 Stream；
                          // 不能让旧的 pending 事件覆盖已签署/已确认条款。
                          status:
                            item.status !== 'pending_signature'
                              ? item.status
                              : request.status,
                          clauses: request.clauses.map((clause) => {
                            const previous = item.clauses.find(
                              (candidate) => candidate.id === clause.id
                            );
                            return previous
                              ? {
                                  ...clause,
                                  listened: previous.listened || clause.listened,
                                  confirmed:
                                    previous.confirmed || clause.confirmed,
                                  understandingStatus:
                                    previous.understandingStatus ??
                                    clause.understandingStatus,
                                  deliveryStatus:
                                    previous.deliveryStatus === 'delivered'
                                      ? 'delivered'
                                      : clause.deliveryStatus,
                                }
                              : clause;
                          }),
                        }
                      : item
                  )
                  : [...current, request],
            },
          };
        }),

      updateConsentRequest: (taskId, formId, updates) =>
        set((state) => ({
          consentRequests: {
            ...state.consentRequests,
            [taskId]: (state.consentRequests[taskId] ?? []).map((item) =>
              item.formId === formId ? { ...item, ...updates } : item
            ),
          },
        })),

      upsertNurseAssistanceRequest: (request) =>
        set((state) => ({
          nurseAssistanceRequests: {
            ...state.nurseAssistanceRequests,
            [request.requestId]: {
              ...state.nurseAssistanceRequests[request.requestId],
              ...request,
              // 旧的 handoff_requested 事件重放不能把已处理请求恢复成请求中。
              status:
                state.nurseAssistanceRequests[request.requestId]?.status ===
                'resolved'
                  ? 'resolved'
                  : request.status,
            },
          },
        })),

      resolveNurseAssistanceRequest: (requestId) =>
        set((state) => {
          const existing = state.nurseAssistanceRequests[requestId];
          if (!existing) return state;
          return {
            nurseAssistanceRequests: {
              ...state.nurseAssistanceRequests,
              [requestId]: { ...existing, status: 'resolved' },
            },
          };
        }),

      markEventHandled: (taskId, eventId) =>
        set((state) => ({
          events: {
            ...state.events,
            [taskId]: (state.events[taskId] ?? []).map((event) =>
              event.id === eventId ? { ...event, handled: true } : event
            ),
          },
        })),

      setFeedback: (taskId, feedback) =>
        set((state) => ({
          feedback: {
            ...Object.fromEntries(
              Object.entries(state.feedback).filter(
                ([, item]) => item.taskId !== taskId
              )
            ),
            ...Object.fromEntries(feedback.map((item) => [item.messageId, item])),
          },
        })),

      saveFeedback: (feedback) =>
        set((state) => ({
          feedback: { ...state.feedback, [feedback.messageId]: feedback },
        })),

      setStreaming: (taskId) => set({ streamingTaskId: taskId }),

      clearSession: (taskId) =>
        set((state) => {
          const sessions = { ...state.sessions };
          const structuredAnswers = { ...state.structuredAnswers };
          const events = { ...state.events };
          const educationCards = { ...state.educationCards };
          const consentRequests = { ...state.consentRequests };
          delete sessions[taskId];
          delete structuredAnswers[taskId];
          delete events[taskId];
          delete educationCards[taskId];
          delete consentRequests[taskId];
          return {
            sessions,
            structuredAnswers,
            events,
            educationCards,
            consentRequests,
            streamingTaskId: null,
          };
        }),

      resetDemoData: () => set(initialState),
    }),
    {
      name: 'medical-evaluate-chat-storage',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        ...state,
        streamingTaskId: null,
      }),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...(persistedState as Partial<ChatStore>),
        streamingTaskId: null,
      }),
    }
  )
);
