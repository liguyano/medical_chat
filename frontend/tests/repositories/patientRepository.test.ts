import { afterEach, describe, expect, it, vi } from 'vitest';

import { mapPatientRecord } from '@/lib/api/mappers';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';
import { MockCareRepository } from '@/lib/repositories/mockRepository';

function okResponse(data: unknown) {
  return new Response(
    JSON.stringify({ code: 'OK', message: '成功', data }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}

const patientInput = {
  patient: {
    hisPatientId: 'HIS-CODEX-1',
    name: '测试患者',
    gender: 'female' as const,
    birthday: '1980-01-02',
    idCardNo: '110101198001020011',
    phone: '13899990001',
    emergencyContactName: '测试家属',
    emergencyContactRelation: '女儿',
    emergencyContactPhone: '13999990001',
    address: '测试地址',
  },
  encounter: {
    inpatientNo: 'ZY-CODEX-1',
    departmentCode: 'CARD',
    department: '心内科',
    ward: '心内病区A',
    bedNo: '99-1',
    admissionDate: '2026-08-20T08:00:00.000Z',
    encounterStatus: 'in_hospital' as const,
    primaryDiagnosis: '冠心病',
    secondaryDiagnoses: ['高血压'],
    riskNote: '注意跌倒',
    admissionSource: '急诊',
    nursingLevel: '一级护理',
    insuranceType: '城镇职工医保',
    allergySummary: '青霉素过敏',
  },
};

describe('patient management repository', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('完整映射患者、住院、安全信息和任务摘要', () => {
    const record = mapPatientRecord({
      patient: {
        id: 9,
        patient_no: 'P0009',
        his_patient_id: 'HIS-9',
        patient_name: '测试患者',
        sex: '女',
        birthday: '1980-01-02',
        id_card_masked: '110***********0011',
        phone: '13899990001',
        emergency_contact_name: '测试家属',
        emergency_contact_relation: '女儿',
        emergency_contact_phone: '13999990001',
        address: '测试地址',
      },
      encounter: {
        id: 19,
        patient_id: 9,
        encounter_no: 'E0019',
        inpatient_no: 'ZY0009',
        department_code: 'CARD',
        department_name: '心内科',
        ward_name: '心内病区A',
        bed_no: '99-1',
        admission_time: '2026-08-20T08:00:00Z',
        encounter_status: '在院',
        diagnosis_snapshot: { primary: '冠心病' },
        nursing_level: '一级护理',
        allergy_summary: '青霉素过敏',
      },
      task_summary: {
        total: 3,
        pending_review: 1,
        in_progress: 1,
        handoff_required: true,
      },
    });

    expect(record.patient).toMatchObject({
      id: '9',
      hisPatientId: 'HIS-9',
      emergencyContactName: '测试家属',
    });
    expect(record.encounter).toMatchObject({
      inpatientNo: 'ZY0009',
      diagnosis: '冠心病',
      nursingLevel: '一级护理',
      allergySummary: '青霉素过敏',
    });
    expect(record.taskSummary).toEqual({
      total: 3,
      pendingReview: 1,
      inProgress: 1,
      handoffRequired: true,
    });
  });

  it('患者新增和编辑按后端契约提交，不回传身份证密文', async () => {
    const dto = {
      patient: {
        id: 9,
        patient_no: 'P0009',
        patient_name: '测试患者',
        sex: '女',
        birthday: '1980-01-02',
        id_card_masked: '110***********0011',
        phone: '13899990001',
      },
      encounter: {
        id: 19,
        patient_id: 9,
        encounter_no: 'E0019',
        inpatient_no: 'ZY-CODEX-1',
        department_name: '心内科',
        ward_name: '心内病区A',
        bed_no: '99-1',
        admission_time: '2026-08-20T08:00:00Z',
        encounter_status: '在院',
        diagnosis_snapshot: { primary: '冠心病' },
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse(dto))
      .mockResolvedValueOnce(okResponse(dto));
    vi.stubGlobal('fetch', fetchMock);
    const repository = new ApiCareRepository();

    await repository.createPatient(patientInput);
    await repository.updatePatient('9', {
      ...patientInput,
      patient: { ...patientInput.patient, idCardNo: undefined },
      encounter: { ...patientInput.encounter, id: '19', bedNo: '99-2' },
    });

    const createBody = JSON.parse(
      String((fetchMock.mock.calls[0][1] as RequestInit).body)
    );
    const updateBody = JSON.parse(
      String((fetchMock.mock.calls[1][1] as RequestInit).body)
    );
    expect(createBody.patient.id_card_no).toBe('110101198001020011');
    expect(createBody.encounter.diagnosis_snapshot.secondary).toEqual([
      '高血压',
    ]);
    expect(updateBody.patient).not.toHaveProperty('id_card_no');
    expect(updateBody.encounter).toMatchObject({ id: 19, bed_no: '99-2' });
  });

  it('患者主动呼叫携带客户端调用编号', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        event_id: 'EVENT-1',
        request_id: 'NURSE-1',
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    await new ApiCareRepository().requestHandoff('109', '需要护士协助', {
      clientInvocationId: 'patient-handoff:click-1',
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      task_id: '109',
      reason: '需要护士协助',
      client_invocation_id: 'patient-handoff:click-1',
    });
  });

  it('Mock 模式支持患者列表、新增、详情和编辑闭环', async () => {
    const repository = new MockCareRepository();
    const created = await repository.createPatient(patientInput);
    const listed = await repository.listPatients({
      keyword: created.patient.patientNo,
      status: '在院',
    });
    const updated = await repository.updatePatient(created.patient.id, {
      ...patientInput,
      patient: { ...patientInput.patient, idCardNo: undefined },
      encounter: {
        ...patientInput.encounter,
        id: created.encounter.id,
        bedNo: '99-3',
      },
    });
    const detail = await repository.getPatient(created.patient.id);

    expect(listed).toHaveLength(1);
    expect(updated.encounter.bedNo).toBe('99-3');
    expect(detail.patient.idCard).toBe(created.patient.idCard);
  });
});
