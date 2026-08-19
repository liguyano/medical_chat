import { describe, expect, it } from 'vitest';
import { patientDemoAccounts } from '@/lib/patient/demoAccounts';
import {
  groupPatientTasks,
  isPatientTaskReadOnly,
} from '@/lib/patient/taskGroups';
import type { CareTask } from '@/lib/types';

function task(id: string, taskStatus: CareTask['taskStatus']): CareTask {
  return {
    id,
    taskNo: `TASK-${id}`,
    patientId: 'patient-1',
    encounterId: 'encounter-1',
    patientName: '演示患者',
    bedNo: '01-1',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus,
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
    createdAt: '2026-08-19T10:00:00Z',
  };
}

describe('患者任务分组', () => {
  it('将待完成、待复核、已完成和已取消任务分开', () => {
    const groups = groupPatientTasks([
      task('pending', 'pending'),
      task('active', 'in_progress'),
      task('review', 'pending_review'),
      task('done', 'completed'),
      task('cancelled', 'cancelled'),
    ]);

    expect(groups.unfinished.map((item) => item.id)).toEqual([
      'pending',
      'active',
    ]);
    expect(groups.completed.map((item) => item.id)).toEqual([
      'review',
      'done',
    ]);
    expect(groups.cancelled.map((item) => item.id)).toEqual(['cancelled']);
  });

  it('只有已提交或已完成的任务进入只读对话模式', () => {
    expect(isPatientTaskReadOnly(task('review', 'pending_review'))).toBe(true);
    expect(isPatientTaskReadOnly(task('done', 'completed'))).toBe(true);
    expect(isPatientTaskReadOnly(task('active', 'in_progress'))).toBe(false);
    expect(isPatientTaskReadOnly()).toBe(false);
  });
});

describe('患者 API 演示身份', () => {
  it('覆盖安装文档列出的十位患者并保留唯一身份证号和手机号', () => {
    expect(patientDemoAccounts).toHaveLength(10);
    expect(new Set(patientDemoAccounts.map((item) => item.idCardNo)).size).toBe(10);
    expect(new Set(patientDemoAccounts.map((item) => item.phone)).size).toBe(10);
    expect(patientDemoAccounts.find((item) => item.name === '周海燕')).toEqual({
      name: '周海燕',
      idCardNo: '110101197206150028',
      phone: '13800000006',
    });
  });
});
