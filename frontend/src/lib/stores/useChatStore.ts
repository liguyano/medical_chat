import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  mockInteractionEvents,
  mockSessions,
  mockStructuredAnswers,
} from '@/lib/mock/dialogue';
import type {
  InteractionEvent,
  InteractionMessage,
  InteractionSession,
  MessageFeedback,
  StructuredAnswer,
} from '@/lib/types';

interface ChatStore {
  sessions: Record<string, InteractionSession>;
  structuredAnswers: Record<string, StructuredAnswer[]>;
  events: Record<string, InteractionEvent[]>;
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
  markEventHandled: (taskId: string, eventId: string) => void;
  saveFeedback: (feedback: MessageFeedback) => void;
  setStreaming: (taskId: string | null) => void;
  clearSession: (taskId: string) => void;
  resetDemoData: () => void;
}

const initialState = {
  sessions: mockSessions,
  structuredAnswers: mockStructuredAnswers,
  events: mockInteractionEvents,
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

      markEventHandled: (taskId, eventId) =>
        set((state) => ({
          events: {
            ...state.events,
            [taskId]: (state.events[taskId] ?? []).map((event) =>
              event.id === eventId ? { ...event, handled: true } : event
            ),
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
          delete sessions[taskId];
          delete structuredAnswers[taskId];
          delete events[taskId];
          return { sessions, structuredAnswers, events, streamingTaskId: null };
        }),

      resetDemoData: () => set(initialState),
    }),
    {
      name: 'medical-evaluate-chat-storage',
    }
  )
);
