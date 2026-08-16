import type { Patient, PatientEncounter, CareTask, AssessmentScale } from '@/lib/types';

/**
 * Mock 患者数据
 */
export const mockPatients: Patient[] = [
  {
    id: '1',
    patientNo: 'P2026080001',
    name: '张小华',
    gender: 'female',
    age: 58,
    idCard: '1234',
    phone: '1380013****',
  },
  {
    id: '2',
    patientNo: 'P2026080002',
    name: '李建国',
    gender: 'male',
    age: 65,
    idCard: '5678',
    phone: '1390014****',
  },
  {
    id: '3',
    patientNo: 'P2026080003',
    name: '王秀英',
    gender: 'female',
    age: 72,
    idCard: '9012',
    phone: '1580015****',
  },
  {
    id: '4',
    patientNo: 'P2026080004',
    name: '赵德华',
    gender: 'male',
    age: 45,
    idCard: '3456',
    phone: '1370016****',
  },
  {
    id: '5',
    patientNo: 'P2026080005',
    name: '陈丽华',
    gender: 'female',
    age: 61,
    idCard: '2468',
    phone: '1360018****',
  },
];

/**
 * Mock 住院记录
 */
export const mockEncounters: PatientEncounter[] = [
  {
    id: '1',
    patientId: '1',
    encounterNo: 'E2026080001',
    inpatientNo: 'IN20260801',
    department: '心内科',
    ward: '心内病区A',
    bedNo: '301-1',
    admissionDate: '2026-08-14T09:30:00',
    diagnosis: '冠心病、高血压',
    encounterStatus: 'in_hospital',
  },
  {
    id: '2',
    patientId: '2',
    encounterNo: 'E2026080002',
    inpatientNo: 'IN20260802',
    department: '心内科',
    ward: '心内病区A',
    bedNo: '302-2',
    admissionDate: '2026-08-15T14:20:00',
    diagnosis: '急性心肌梗死',
    encounterStatus: 'in_hospital',
  },
  {
    id: '3',
    patientId: '3',
    encounterNo: 'E2026080003',
    inpatientNo: 'IN20260803',
    department: '心内科',
    ward: '心内病区B',
    bedNo: '401-3',
    admissionDate: '2026-08-16T08:00:00',
    diagnosis: '心房颤动、心力衰竭',
    encounterStatus: 'in_hospital',
  },
  {
    id: '4',
    patientId: '4',
    encounterNo: 'E2026080004',
    inpatientNo: 'IN20260804',
    department: '心内科',
    ward: '心内病区A',
    bedNo: '301-4',
    admissionDate: '2026-08-13T16:45:00',
    diagnosis: '冠心病',
    encounterStatus: 'in_hospital',
  },
  {
    id: '5',
    patientId: '5',
    encounterNo: 'E2026080005',
    inpatientNo: 'IN20260805',
    department: '心内科',
    ward: '心内病区B',
    bedNo: '405-2',
    admissionDate: '2026-08-16T11:15:00',
    diagnosis: '冠状动脉粥样硬化性心脏病',
    encounterStatus: 'in_hospital',
  },
];

/**
 * Mock 护理任务
 */
export const mockTasks: CareTask[] = [
  {
    id: '1',
    taskNo: 'T2026080001',
    patientId: '1',
    encounterId: '1',
    encounterNo: 'IN20260801',
    patientName: '张小华',
    bedNo: '301-1',
    department: '心内科',
    wardName: '心内病区A',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus: 'in_progress',
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
    scaleId: '1',
    scaleName: '入院评估任务包',
    scaleVersion: 'v1.0',
    scaleIds: ['1', '2', '3', '4', '5'],
    scaleNames: ['入院评估单', 'ADL日常生活能力', 'NRS2002营养风险', 'Braden压疮风险', '跌倒/坠床风险'],
    participantType: 'patient',
    participantName: '张小华',
    assessmentScene: 'admission',
    consentRequired: true,
    educationTopics: ['药物过敏安全宣教', '住院禁烟宣教'],
    plannedStartTime: '2026-08-16T10:10:00',
    currentStage: 'ask',
    createdAt: '2026-08-16T10:00:00',
    progress: {
      current: 8,
      total: 20,
    },
  },
  {
    id: '2',
    taskNo: 'T2026080002',
    patientId: '2',
    encounterId: '2',
    encounterNo: 'IN20260802',
    patientName: '李建国',
    bedNo: '302-2',
    department: '心内科',
    wardName: '心内病区A',
    taskType: '入院评估',
    collectionMode: 'traditional_form',
    taskStatus: 'pending',
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
    scaleId: '1',
    scaleName: '入院评估任务包',
    scaleVersion: 'v1.0',
    scaleIds: ['1', '2', '5'],
    scaleNames: ['入院评估单', 'ADL日常生活能力', '跌倒/坠床风险'],
    participantType: 'patient',
    participantName: '李建国',
    assessmentScene: 'admission',
    consentRequired: true,
    educationTopics: ['防跌倒宣教'],
    plannedStartTime: '2026-08-16T11:00:00',
    createdAt: '2026-08-16T10:30:00',
  },
  {
    id: '3',
    taskNo: 'T2026080003',
    patientId: '3',
    encounterId: '3',
    encounterNo: 'IN20260803',
    patientName: '王秀英',
    bedNo: '401-3',
    department: '心内科',
    wardName: '心内病区B',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus: 'pending_review',
    assignedNurseId: 'N002',
    assignedNurseName: '王护士',
    scaleId: '1',
    scaleName: '入院评估任务包',
    scaleVersion: 'v1.0',
    scaleIds: ['1', '2', '3', '4', '5'],
    scaleNames: ['入院评估单', 'ADL日常生活能力', 'NRS2002营养风险', 'Braden压疮风险', '跌倒/坠床风险'],
    participantType: 'family',
    participantName: '王秀英家属',
    relationshipToPatient: '女儿',
    assessmentScene: 'admission',
    consentRequired: true,
    educationTopics: ['防跌倒宣教', '用药安全宣教'],
    currentStage: 'exit',
    aiSummary: '患者由女儿协助完成评估，存在跌倒风险和夜间下床需求，建议护士进一步确认步态与用药情况。',
    createdAt: '2026-08-16T08:30:00',
    progress: {
      current: 20,
      total: 20,
    },
  },
  {
    id: '4',
    taskNo: 'T2026080004',
    patientId: '4',
    encounterId: '4',
    encounterNo: 'IN20260804',
    patientName: '赵德华',
    bedNo: '301-4',
    department: '心内科',
    wardName: '心内病区A',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus: 'completed',
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
    scaleId: '1',
    scaleName: '入院评估任务包',
    scaleVersion: 'v1.0',
    scaleIds: ['1', '2', '3'],
    scaleNames: ['入院评估单', 'ADL日常生活能力', 'NRS2002营养风险'],
    participantType: 'patient',
    participantName: '赵德华',
    assessmentScene: 'admission',
    consentRequired: false,
    educationTopics: ['冠心病住院生活宣教'],
    currentStage: 'exit',
    aiSummary: '评估过程顺利，患者沟通清晰，自理能力良好，已完成住院生活宣教。',
    createdAt: '2026-08-15T14:00:00',
    completedAt: '2026-08-15T14:35:00',
    progress: {
      current: 20,
      total: 20,
    },
  },
];

/**
 * Mock 量表配置
 */
export const mockScales: AssessmentScale[] = [
  {
    id: '1',
    scaleCode: 'ADMISSION_GENERAL',
    scaleName: '入院评估单',
    scaleType: 'general',
    description: '患者入院时的基本信息和一般状况评估',
  },
  {
    id: '2',
    scaleCode: 'ADL',
    scaleName: 'ADL日常生活能力',
    scaleType: 'ability',
    description: '评估进食、穿衣、活动和个人卫生等日常生活能力',
  },
  {
    id: '3',
    scaleCode: 'NRS2002',
    scaleName: 'NRS2002营养风险',
    scaleType: 'risk',
    description: '评估营养状态、疾病严重程度和年龄风险',
  },
  {
    id: '4',
    scaleCode: 'BRADEN_PRESSURE',
    scaleName: 'Braden压疮风险',
    scaleType: 'risk',
    description: '评估感觉、潮湿、活动、营养和摩擦剪切风险',
  },
  {
    id: '5',
    scaleCode: 'FALL_RISK',
    scaleName: '跌倒/坠床风险',
    scaleType: 'risk',
    description: '评估既往跌倒、步态、认知、药物和环境风险',
  },
];

/**
 * 根据患者ID获取住院记录
 */
export function getEncounterByPatientId(patientId: string): PatientEncounter | undefined {
  return mockEncounters.find((enc) => enc.patientId === patientId);
}

/**
 * 根据任务ID获取任务
 */
export function getTaskById(taskId: string): CareTask | undefined {
  return mockTasks.find((task) => task.id === taskId);
}

/**
 * 根据患者ID获取患者
 */
export function getPatientById(patientId: string): Patient | undefined {
  return mockPatients.find((patient) => patient.id === patientId);
}
