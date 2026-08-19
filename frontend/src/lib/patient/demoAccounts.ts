export interface PatientDemoAccount {
  name: string;
  idCardNo: string;
  phone: string;
}

/**
 * 与 deploy/Install.md 中的本地 API 演示患者保持一致。
 * 这些数据只用于本地联调，不可用于生产环境。
 */
export const patientDemoAccounts: PatientDemoAccount[] = [
  { name: '张桂芳', idCardNo: '110101194803120010', phone: '13800000001' },
  { name: '李国强', idCardNo: '110101195507250026', phone: '13800000002' },
  { name: '王秀兰', idCardNo: '110101194011020038', phone: '13800000003' },
  { name: '陈建军', idCardNo: '110101196801180043', phone: '13800000004' },
  { name: '赵敏', idCardNo: '110101198509300051', phone: '13800000005' },
  { name: '周海燕', idCardNo: '110101197206150028', phone: '13800000006' },
  { name: '孙志伟', idCardNo: '110101196212080035', phone: '13800000007' },
  { name: '杨秀梅', idCardNo: '110101197904220026', phone: '13800000008' },
  { name: '黄建国', idCardNo: '110101195010090019', phone: '13800000009' },
  { name: '林晓莉', idCardNo: '11010119920214002X', phone: '13800000010' },
];
