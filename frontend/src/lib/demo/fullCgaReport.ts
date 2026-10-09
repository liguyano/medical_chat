import type { AssessmentReport } from '@/lib/types';
import type { AssessmentScaleSnapshot } from '@/lib/assessmentReportView';

const assessedAt = '2026-10-09T09:30:00+08:00';

function scale(
  code: string,
  name: string,
  summary: string,
  scoreValue: number,
  maxScore: number | null,
  questions: Array<[string, string, number, boolean?]>,
  riskLevel = '正常'
): AssessmentScaleSnapshot {
  return {
    scale_code: code,
    scale_name: name,
    result_summary: summary,
    risk_level: riskLevel,
    score_status: 'complete',
    assessor_name: '李护士',
    assessed_at: assessedAt,
    scores: [{
      score_name: '总分',
      score_value: scoreValue,
      max_score: maxScore,
      interpretation: summary,
    }],
    answers: questions.map(([question, value, clinical_score, abnormal = false]) => ({
      question,
      value,
      clinical_score,
      abnormal,
    })),
  };
}

const assessments: AssessmentScaleSnapshot[] = [
  scale('phq9', '抑郁评分量表（PHQ-9）', '无抑郁症状', 2, 27, [
    ['做事缺乏兴趣或乐趣', '完全没有', 0],
    ['感到心情低落、沮丧或绝望', '偶尔几天', 1],
  ]),
  scale('3d_cam', '谵妄评估（3D-CAM）', '未发现谵妄表现', 0, 4, [
    ['精神状态是否急性改变', '否', 0],
    ['注意力是否明显不集中', '否', 0],
  ]),
  scale('gad7', '广泛性焦虑自评量表（GAD-7）', '无明显焦虑', 3, 21, [
    ['感到紧张、焦虑或急切', '偶尔几天', 1],
    ['无法停止或控制担忧', '完全没有', 0],
  ]),
  scale('mini_cog', '简易智力状态评估表 Mini-Cog', '认知筛查正常', 5, 5, [
    ['三词回忆', '三个词均能回忆', 3],
    ['画钟测试', '数字与指针位置正确', 2],
  ]),
  scale('mmse', '简易智能精神状态检查量表（MMSE）', '认知功能正常', 28, 30, [
    ['时间与地点定向', '回答正确', 10],
    ['记忆与回忆', '完成良好', 6],
  ]),
  scale('adl', 'Barthel 指数 / 日常生活能力（ADL）', '轻度依赖', 85, 100, [
    ['进食', '可独立完成', 10],
    ['床椅转移', '需要少量协助', 10, true],
    ['上下楼梯', '需要协助', 5, true],
  ], '轻度功能受限'),
  scale('iadl_lawton_brody', 'Lawton-Brody IADL 量表', '工具性日常生活能力轻度受限', 6, 8, [
    ['使用电话', '可独立使用', 1],
    ['购物', '需要家属陪同', 0, true],
  ], '需要关注'),
  scale('water_swallow_test', '洼田饮水试验', '吞咽功能正常', 1, 5, [
    ['30ml 饮水表现', '一次顺利饮完，无呛咳', 1],
  ]),
  scale('fall_risk', '跌倒/坠床风险评估量表', '低度跌倒风险', 30, 125, [
    ['近三个月跌倒史', '无', 0],
    ['行走辅助', '偶尔使用手杖', 15, true],
  ], '低风险'),
  scale('tug', 'TUG“起立-行走”计时测试', '移动能力正常', 11, 30, [
    ['起立行走计时', '11 秒', 11],
  ]),
  scale('sppb', 'SPPB 评分细则', '躯体功能轻度受限', 9, 12, [
    ['平衡测试', '并脚及半串联站立完成', 3],
    ['4 米步行测试', '5.1 秒', 3],
  ], '轻度受限'),
  scale('grip_strength', '握力测量', '握力处于正常范围', 21, null, [
    ['优势手握力', '21.0 kg', 21],
  ]),
  scale('sarcopenia', '肌少症评估', '未发现肌少症', 1, 10, [
    ['提起 5 kg 重物', '无困难', 0],
    ['步行穿过房间', '无困难', 0],
  ]),
  scale('simple_vision', '视力简易评估表', '矫正视力可满足日常生活', 2, 3, [
    ['看远处标识', '佩戴眼镜后可看清', 1],
    ['阅读药品说明', '字体过小时略困难', 1, true],
  ], '轻度受限'),
  scale('simple_hearing', '听力简易评估表', '日常交流听力正常', 3, 3, [
    ['正常音量交谈', '能够听清', 1],
    ['安静环境耳语', '能够辨认', 1],
  ]),
  scale('iciq_sf', '国际尿失禁咨询委员会尿失禁问卷简表（ICIQ-SF）', '无尿失禁', 0, 21, [
    ['漏尿频率', '从不', 0],
    ['漏尿对生活的影响', '无影响', 0],
  ]),
  scale('ccf_fis', '大便失禁评分（CCF-FIS）', '无大便失禁', 0, 20, [
    ['固体便失禁', '从不', 0],
    ['液体便失禁', '从不', 0],
  ]),
  scale('constipation_symptoms', '便秘症状评估表', '未发现便秘', 1, 12, [
    ['每周排便次数', '每周 5 至 6 次', 0],
    ['排便是否费力', '偶尔', 1],
  ]),
  scale('pain_nrs', '疼痛强度评估（NRS）', '轻微疼痛', 2, 10, [
    ['当前疼痛强度', '2 分，偶有膝关节酸痛', 2, true],
  ], '轻度疼痛'),
  scale('frail', 'FRAIL 衰弱量表', '衰弱前期', 1, 5, [
    ['疲劳感', '偶尔感到疲劳', 1, true],
    ['过去一年非计划体重下降', '无', 0],
  ], '需要关注'),
  scale('braden', '压疮危险因素（Braden Scale）', '压疮风险较低', 19, 23, [
    ['感觉感知', '无损害', 4],
    ['活动能力', '偶尔步行', 3],
  ], '低风险'),
  scale('osteoporosis_risk', '骨质疏松风险评估', '存在中等骨质疏松风险', 4, 10, [
    ['年龄风险', '76 岁', 2, true],
    ['既往脆性骨折', '无', 0],
  ], '中风险'),
  scale('athens_insomnia', '睡眠自测 AIS 量表', '无失眠障碍', 4, 24, [
    ['入睡时间', '约 20 分钟', 1],
    ['夜间醒来', '偶尔一次', 1],
  ]),
  scale('nrs2002', '营养风险筛查评分简表（NRS2002）', '无营养风险', 1, 7, [
    ['近期体重下降', '无明显下降', 0],
    ['近期进食量减少', '轻微减少', 1],
  ], '低风险'),
  scale('mna_sf', '微营养评定法简表（MNA-SF）', '营养状况正常', 12, 14, [
    ['食物摄入是否减少', '无明显减少', 2],
    ['活动能力', '可以外出', 2],
  ]),
  scale('family_apgar', '家庭关怀评估（APGAR）', '家庭功能良好', 8, 10, [
    ['需要帮助时家人支持程度', '经常能够获得支持', 2],
    ['家庭共同解决问题情况', '多数时候可以', 2],
  ]),
  scale('home_environment_screening', '居家环境筛查表', '居家环境总体安全', 13, 15, [
    ['卫生间是否有扶手', '已安装扶手', 2],
    ['夜间通道照明', '有感应夜灯', 2],
  ], '低风险'),
];

export const fullCgaDemoReport: AssessmentReport = {
  id: 9001,
  versionNo: 1,
  reportStatus: 'confirmed',
  generatedBy: 'demo:qwen-plus',
  generatedAt: '2026-10-09T10:10:00+08:00',
  confirmedBy: 1,
  confirmedAt: '2026-10-09T10:20:00+08:00',
  reportNo: 'REPORT-CGA-DEMO-001',
  taskId: 9001,
  sourceSubmissionIds: [],
  sourceSnapshot: {
    patient: {
      name: '林安华（演示）',
      sex: '女',
      age: 76,
      department: '老年医学科',
      ward: '老年综合病区',
      bed_no: '08-1',
      inpatient_no: 'DEMO-20261009',
      diagnosis: '高血压病、膝关节退行性改变',
    },
    assessments,
  },
  reportContent: {
    overallSummary: '患者意识清楚，认知、情绪、吞咽、听力及营养状态总体稳定。日常生活能力和工具性日常生活能力轻度受限，行走时偶尔使用手杖；同时存在衰弱前期、中等骨质疏松风险和轻微膝关节疼痛，应重点做好活动安全、骨健康和功能维持。',
    keyFindings: [
      '认知筛查、情绪筛查和谵妄评估未见明显异常。',
      'Barthel 指数 85 分，床椅转移和上下楼梯需要少量协助。',
      'FRAIL 量表提示衰弱前期，建议维持规律活动并动态复评。',
    ],
    riskOverview: [
      '跌倒风险较低，但使用手杖及楼梯活动时仍需关注安全。',
      '骨质疏松风险为中等，需结合骨密度及实验室检查进一步评估。',
      'Braden 评分 19 分，当前压疮风险较低。',
    ],
    nursingFocus: [
      '指导安全转移、正确使用手杖，并保持病区通道整洁。',
      '关注膝关节疼痛变化，按计划开展耐力和平衡训练。',
      '继续观察睡眠、营养摄入和活动耐量。',
    ],
    followUpSuggestions: [
      '住院期间每周复评跌倒风险和生活自理能力。',
      '根据医嘱完善骨密度检查及骨健康管理。',
      '出院前与患者及家属共同确认居家防跌倒措施。',
    ],
  },
  versions: [{
    id: 9001,
    versionNo: 1,
    reportStatus: 'confirmed',
    generatedBy: 'demo:qwen-plus',
    generatedAt: '2026-10-09T10:10:00+08:00',
    confirmedBy: 1,
    confirmedAt: '2026-10-09T10:20:00+08:00',
  }],
};
