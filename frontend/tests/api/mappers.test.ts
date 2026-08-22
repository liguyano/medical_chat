import { describe, expect, it } from 'vitest';
import {
  mapCreateTaskRequest,
  mapMessageRating,
  mapExtractedField,
  mapPatientPortal,
  mapQualityReview,
  mapTaskDto,
  toCollectionMode,
  toReviewerId,
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

  it('将演示护士工号转换为质评接口数值ID', () => {
    expect(toReviewerId('N001')).toBe(1);
    expect(toReviewerId('2001')).toBe(2001);
    expect(toReviewerId(undefined)).toBe(0);
  });

  it('将后端数字ID统一映射为字符串', () => {
    const task = mapTaskDto({
      task_id: 900719925474099,
      task_no: 'TASK-1',
      session_id: 88,
      patient_id: 12,
      encounter_id: 13,
      inpatient_no: 'ZY000012',
      sex: '女',
      age: 68,
      admission_time: '2026-08-19T08:30:00+08:00',
      encounter_status: '在院中',
      scale_progress: [
        {
          scale_id: 5,
          scale_name: 'Braden压疮评估量表',
          answered_question_count: 3,
          total_question_count: 6,
          status: 'collecting',
        },
      ],
      collection_mode: 'ai_dialogue',
      task_status: 'pending',
      assigned_nurse_id: 14,
      created_at: '2026-08-16T10:00:00Z',
      preparation: {
        status: 'running',
        stage: 'dialog_preheat',
        attempt: 1,
        error: null,
        stages: {
          schedule_prepare: {
            status: 'completed',
            output: {
              question_count: 3,
              questions: [{ question_name: '跌倒风险' }],
            },
            updated_at: '2026-08-19T08:31:00Z',
          },
          dialog_preheat: {
            status: 'running',
            output: {},
          },
          dialog_opening: {
            status: 'pending',
            output: {},
          },
        },
      },
    });
    expect(task.id).toBe('900719925474099');
    expect(task.sessionId).toBe('88');
    expect(task.patientId).toBe('12');
    expect(task.assignedNurseId).toBe('14');
    expect(task.inpatientNo).toBe('ZY000012');
    expect(task.sex).toBe('女');
    expect(task.age).toBe(68);
    expect(task.admissionDate).toBe('2026-08-19T08:30:00+08:00');
    expect(task.scaleProgress?.[0]).toMatchObject({
      scaleId: '5',
      answeredQuestionCount: 3,
      totalQuestionCount: 6,
      status: 'collecting',
    });
    expect(task.preparation?.status).toBe('running');
    expect(task.preparation?.stages.schedule_prepare.output).toMatchObject({
      question_count: 3,
    });
  });

  it('映射患者登录后的住院信息和本人任务', () => {
    const portal = mapPatientPortal({
      patient: {
        id: 4,
        patient_no: 'P-DEMO-0004',
        patient_name: '陈建军',
        sex: '男',
        birthday: '1968-01-18',
        phone: '13800000004',
      },
      encounter: {
        id: 8,
        encounter_no: 'E-DEMO-0004',
        inpatient_no: 'ZY0004',
        patient_id: 4,
        department_name: '呼吸与危重症医学科',
        ward_name: '呼吸内科病区',
        bed_no: '16-1',
        admission_time: '2026-08-17T10:00:00Z',
        encounter_status: '在院',
      },
      tasks: [
        {
          task_id: 10,
          task_no: 'TASK-1',
          session_id: 'SESS-1',
          patient_id: 4,
          encounter_id: 8,
          collection_mode: 'ai_dialogue',
          task_status: 'in_progress',
          created_at: '2026-08-18T10:00:00Z',
        },
      ],
    });

    expect(portal.patient.id).toBe('4');
    expect(portal.encounter.inpatientNo).toBe('ZY0004');
    expect(portal.tasks[0].id).toBe('10');
    expect(portal.tasks[0].sessionId).toBe('SESS-1');
  });

  it('映射逐条消息质评与整体质量评价', () => {
    const feedback = mapMessageRating({
      feedback_id: 10,
      task_id: 3,
      message_id: 'MSG-1',
      reviewer_id: 1,
      rating: 'dislike',
      score: 2,
      issue_tags: ['追问不合理'],
      comment: '应先确认症状持续时间',
      reviewed_at: '2026-08-18T10:00:00Z',
    });
    expect(feedback.messageId).toBe('MSG-1');
    expect(feedback.score).toBe(2);
    expect(feedback.issueTags).toEqual(['追问不合理']);

    const review = mapQualityReview({
      task_id: 3,
      reviewer_id: 1,
      dialogue_scores: { 追问合理性: 4 },
      assessment_scores: { 答案完整性: 5 },
      dialogue_comments: { 追问合理性: '基本合理' },
      submitted_at: '2026-08-18T11:00:00Z',
    });
    expect(review.taskId).toBe('3');
    expect(review.dialogueScores['追问合理性']).toBe(4);
    expect(review.submittedAt).toBe('2026-08-18T11:00:00Z');
  });

  it('结构化答案优先使用量表真实显示值并保留编码审计信息', () => {
    const answer = mapExtractedField({
      field_id: 1,
      question_id: 2,
      question_code: 'smoking_years',
      question_text: '抽烟烟龄',
      selected_options: ['option_3'],
      selected_option_labels: ['10年以上'],
      selected_option_values: ['10年以上'],
      display_value: '10年以上',
      source_message_ids: ['MSG-1'],
      confidence: 0.95,
    });
    expect(answer.displayValue).toBe('10年以上');
    expect(answer.selectedOptionLabels).toEqual(['10年以上']);
    expect(answer.selectedOptions).toEqual(['option_3']);
  });
});
