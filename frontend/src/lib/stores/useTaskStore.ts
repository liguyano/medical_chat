import { create } from 'zustand';
import type { CareTask } from '@/lib/types';

interface TaskStore {
  tasks: CareTask[];
  currentTask: CareTask | null;
  setTasks: (tasks: CareTask[]) => void;
  setCurrentTask: (task: CareTask | null) => void;
  updateTaskStatus: (taskId: string, status: CareTask['taskStatus']) => void;
  updateTaskProgress: (taskId: string, current: number, total: number) => void;
}

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: [],
  currentTask: null,

  setTasks: (tasks) => set({ tasks }),

  setCurrentTask: (task) => set({ currentTask: task }),

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
}));
