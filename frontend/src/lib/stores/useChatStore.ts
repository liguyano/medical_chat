import { create } from 'zustand';
import type { InteractionSession, InteractionMessage, StructuredAnswer } from '@/lib/types';

interface ChatStore {
  session: InteractionSession | null;
  structuredAnswers: StructuredAnswer[];
  isStreaming: boolean;

  setSession: (session: InteractionSession) => void;
  addMessage: (message: InteractionMessage) => void;
  updateMessage: (messageId: string, updates: Partial<InteractionMessage>) => void;
  setStructuredAnswers: (answers: StructuredAnswer[]) => void;
  updateStructuredAnswer: (questionId: string, updates: Partial<StructuredAnswer>) => void;
  setStreaming: (isStreaming: boolean) => void;
  clearSession: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  session: null,
  structuredAnswers: [],
  isStreaming: false,

  setSession: (session) => set({ session }),

  addMessage: (message) =>
    set((state) => ({
      session: state.session
        ? {
            ...state.session,
            messages: [...state.session.messages, message],
          }
        : null,
    })),

  updateMessage: (messageId, updates) =>
    set((state) => ({
      session: state.session
        ? {
            ...state.session,
            messages: state.session.messages.map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg
            ),
          }
        : null,
    })),

  setStructuredAnswers: (answers) => set({ structuredAnswers: answers }),

  updateStructuredAnswer: (questionId, updates) =>
    set((state) => ({
      structuredAnswers: state.structuredAnswers.map((answer) =>
        answer.questionId === questionId ? { ...answer, ...updates } : answer
      ),
    })),

  setStreaming: (isStreaming) => set({ isStreaming }),

  clearSession: () =>
    set({
      session: null,
      structuredAnswers: [],
      isStreaming: false,
    }),
}));
