import type { CareTask } from '@/lib/types';

export interface PatientTaskGroups {
  unfinished: CareTask[];
  completed: CareTask[];
  cancelled: CareTask[];
}

export function groupPatientTasks(tasks: CareTask[]): PatientTaskGroups {
  return tasks.reduce<PatientTaskGroups>(
    (groups, task) => {
      if (
        task.taskStatus === 'pending_review' ||
        task.taskStatus === 'completed'
      ) {
        groups.completed.push(task);
      } else if (task.taskStatus === 'cancelled') {
        groups.cancelled.push(task);
      } else {
        groups.unfinished.push(task);
      }
      return groups;
    },
    { unfinished: [], completed: [], cancelled: [] }
  );
}

export function isPatientTaskReadOnly(task?: CareTask): boolean {
  return task?.taskStatus === 'pending_review' || task?.taskStatus === 'completed';
}
