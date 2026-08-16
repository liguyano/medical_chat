import type { Patient, PatientEncounter, CareTask, AssessmentScale } from '@/lib/types';
import { generateId } from '@/lib/utils';

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
    patientName: '张小华',
    bedNo: '301-1',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus: 'in_progress',
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
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
    patientName: '李建国',
    bedNo: '302-2',
    taskType: '入院评估',
    collectionMode: 'traditional_form',
    taskStatus: 'pending',
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
    createdAt: '2026-08-16T10:30:00',
  },
  {
    id: '3',
    taskNo: 'T2026080003',
    patientId: '3',
    encounterId: '3',
    patientName: '王秀英',
    bedNo: '401-3',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus: 'pending_review',
    assignedNurseId: 'N002',
    assignedNurseName: '王护士',
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
    patientName: '赵德华',
    bedNo: '301-4',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue',
    taskStatus: 'completed',
    assignedNurseId: 'N001',
    assignedNurseName: '李护士',
    createdAt: '2026-08-15T14:00:00',
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
    scaleName: '入院一般评估',
    scaleType: 'general',
    description: '患者入院时的基本信息和一般状况评估',
  },
  {
    id: '2',
    scaleCode: 'MORSE_FALL',
    scaleName: 'Morse跌倒风险评估',
    scaleType: 'risk',
    description: '评估患者跌倒风险',
  },
  {
    id: '3',
    scaleCode: 'BRADEN_PRESSURE',
    scaleName: 'Braden压疮风险评估',
    scaleType: 'risk',
    description: '评估患者压疮风险',
  },
  {
    id: '4',
    scaleCode: 'VTE_RISK',
    scaleName: 'VTE风险评估',
    scaleType: 'risk',
    description: '评估患者静脉血栓栓塞风险',
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
