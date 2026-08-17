import { describe, expect, it } from 'vitest';
import {
  mapCreateTaskRequest,
  mapTaskDto,
  toCollectionMode,
} from '@/lib/api/mappers';

describe('API mappers', () => {
  it('转换前后端采集模式命名', () => {
    expect(toCollectionMode('traditional_form')).toBe('traditional_form');
    expect(toCollectionMode('ai_dialogue')).toBe('ai_dialogue');
    const request = mapCreateTaskRequest({
      patient_id: '1',
      encounter_id: '2',
      assigned_nurse_id: '3',
      scale_ids: ['4'],
      collection_mode: 'ai_dialogue',
      participant_type: 'patient',
      assessment_scene: 'admission',
    });
    expect(request.collection_mode).toBe('ai_dialogue');
    expect(request.patient_id).toBe(1);
    expect(request.encounter_id).toBe(2);
    expect(request.assigned_nurse_id).toBe(3);
    expect(request.scale_ids).toEqual([4]);
  });

  it('非数字护士编码不会冒充数据库主键', () => {
    const request = mapCreateTaskRequest({
      patient_id: '1',
      encounter_id: '2',
      assigned_nurse_id: 'N001',
      scale_ids: ['4'],
      collection_mode: 'ai_dialogue',
      participant_type: 'patient',
      assessment_scene: 'admission',
    });
    expect(request.assigned_nurse_id).toBeUndefined();
  });

  it('将后端数字ID统一映射为字符串', () => {
    const task = mapTaskDto({
      task_id: 900719925474099,
      task_no: 'TASK-1',
      session_id: 88,
      patient_id: 12,
      encounter_id: 13,
      collection_mode: 'ai_dialogue',
      task_status: 'pending',
      assigned_nurse_id: 14,
      created_at: '2026-08-16T10:00:00Z',
    });
    expect(task.id).toBe('900719925474099');
    expect(task.sessionId).toBe('88');
    expect(task.patientId).toBe('12');
    expect(task.assignedNurseId).toBe('14');
  });
});
