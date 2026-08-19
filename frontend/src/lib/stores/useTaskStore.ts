import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { mockTasks } from '@/lib/mock/data';
import type {
  AssessmentReview,
  CareTask,
  ConsentProgress,
  PrototypeAnswerValue,
  QualityReview,
} from '@/lib/types';

interface TaskStore {
  tasks: CareTask[];
  currentTask: CareTask | null;
  formDrafts: Record<string, Record<string, PrototypeAnswerValue>>;
  submittedAnswers: Record<string, Record<string, PrototypeAnswerValue>>;
  reviews: Record<string, AssessmentReview>;
  qualityReviews: Record<string, QualityReview>;
  consents: Record<string, ConsentProgress>;
  setTasks: (tasks: CareTask[]) => void;
  addTask: (task: CareTask) => void;
  upsertTask: (task: CareTask) => void;
  setCurrentTask: (task: CareTask | null) => void;
  updateTask: (taskId: string, updates: Partial<CareTask>) => void;
  updateTaskStatus: (taskId: string, status: CareTask['taskStatus']) => void;
  updateTaskProgress: (taskId: string, current: number, total: number) => void;
  saveFormAnswer: (taskId: string, questionId: string, value: PrototypeAnswerValue) => void;
  submitForm: (taskId: string, total: number) => void;
  saveReview: (review: AssessmentReview) => void;
  saveQualityReview: (review: QualityReview) => void;
  clearQualityReview: (taskId: string) => void;
  saveConsent: (consent: ConsentProgress) => void;
  requestHandoff: (
    taskId: string,
    reason: string,
    details?: {
      requestId?: string;
      requestedAction?: string;
      actionLabel?: string;
      urgency?: 'routine' | 'urgent';
    }
  ) => void;
  resolveHandoff: (taskId: string) => void;
  resetDemoData: () => void;
}

const initialState = {
  tasks: mockTasks,
  currentTask: null,
  formDrafts: {},
  submittedAnswers: {},
  reviews: {},
  qualityReviews: {},
  consents: {},
};

export const useTaskStore = create<TaskStore>()(
  persist(
    (set) => ({
      ...initialState,

      setTasks: (tasks) => set({ tasks }),

      addTask: (task) =>
        set((state) => ({
          tasks: [task, ...state.tasks],
          currentTask: task,
        })),

      upsertTask: (task) =>
        set((state) => ({
          tasks: state.tasks.some((item) => item.id === task.id)
            ? state.tasks.map((item) => (item.id === task.id ? task : item))
            : [task, ...state.tasks],
          currentTask:
            state.currentTask?.id === task.id ? task : state.currentTask,
        })),

      setCurrentTask: (task) => set({ currentTask: task }),

      updateTask: (taskId, updates) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === taskId
              ? { ...task, ...updates, updatedAt: new Date().toISOString() }
              : task
          ),
          currentTask:
            state.currentTask?.id === taskId
              ? { ...state.currentTask, ...updates, updatedAt: new Date().toISOString() }
              : state.currentTask,
        })),

      updateTaskStatus: (taskId, status) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === taskId ? { ...task, taskStatus: status } : task
          ),
          currentTask:
            state.currentTask?.id === taskId
              ? { ...state.currentTask, taskStatus: status }
              : state.currentTask,
        })),

      updateTaskProgress: (taskId, current, total) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === taskId ? { ...task, progress: { current, total } } : task
          ),
          currentTask:
            state.currentTask?.id === taskId
              ? { ...state.currentTask, progress: { current, total } }
              : state.currentTask,
        })),

      saveFormAnswer: (taskId, questionId, value) =>
        set((state) => ({
          formDrafts: {
            ...state.formDrafts,
            [taskId]: {
              ...(state.formDrafts[taskId] ?? {}),
              [questionId]: value,
            },
          },
        })),

      submitForm: (taskId, total) =>
        set((state) => ({
          submittedAnswers: {
            ...state.submittedAnswers,
            [taskId]: { ...(state.formDrafts[taskId] ?? {}) },
          },
          tasks: state.tasks.map((task) =>
            task.id === taskId
              ? {
                  ...task,
                  taskStatus: 'pending_review',
                  progress: { current: total, total },
                  updatedAt: new Date().toISOString(),
                }
              : task
          ),
        })),

      saveReview: (review) =>
        set((state) => ({
          reviews: { ...state.reviews, [review.taskId]: review },
          tasks: state.tasks.map((task) =>
            task.id === review.taskId
              ? {
                  ...task,
                  taskStatus:
                    review.status === 'confirmed'
                      ? 'completed'
                      : review.status === 'returned'
                        ? 'in_progress'
                        : task.taskStatus,
                  completedAt:
                    review.status === 'confirmed' ? new Date().toISOString() : task.completedAt,
                }
              : task
          ),
        })),

      saveQualityReview: (review) =>
        set((state) => ({
          qualityReviews: { ...state.qualityReviews, [review.taskId]: review },
        })),

      clearQualityReview: (taskId) =>
        set((state) => ({
          qualityReviews: Object.fromEntries(
            Object.entries(state.qualityReviews).filter(
              ([reviewTaskId]) => reviewTaskId !== taskId
            )
          ),
        })),

      saveConsent: (consent) =>
        set((state) => ({
          consents: { ...state.consents, [consent.taskId]: consent },
        })),

      requestHandoff: (taskId, reason, details) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === taskId
              ? {
                  ...task,
                  handoffRequired: true,
                  handoffReason: reason,
                  handoffRequestId: details?.requestId,
                  handoffRequestedAction: details?.requestedAction,
                  handoffActionLabel: details?.actionLabel,
                  handoffUrgency: details?.urgency,
                }
              : task
          ),
        })),

      resolveHandoff: (taskId) =>
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.id === taskId
              ? {
                  ...task,
                  handoffRequired: false,
                  handoffReason: undefined,
                  handoffRequestId: undefined,
                  handoffRequestedAction: undefined,
                  handoffActionLabel: undefined,
                  handoffUrgency: undefined,
                }
              : task
          ),
        })),

      resetDemoData: () => set({ ...initialState, tasks: [...mockTasks] }),
    }),
    {
      name: 'medical-evaluate-task-storage',
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
