# 前端交互原型开发方案

> **目标：** 基于Mock数据构建专业级前端原型，验证"护士发起任务 → 患者AI对话评估 → 护士实时监控复核"的完整交互流程，展现现代化医疗场景的视觉与交互体验。

## 1. 技术栈与架构

### 1.1 核心技术

| 技术 | 版本/方案 | 用途 |
|------|----------|------|
| **框架** | Next.js 16.3.1 (App Router) | SSR/SSG、路由、API Routes模拟后端 |
| **语言** | TypeScript 5.x | 类型安全 |
| **样式** | Tailwind CSS 4.x | 原子化CSS、响应式设计 |
| **状态管理** | Zustand + React Context | 全局状态（用户/任务）+ 局部状态（对话） |
| **UI组件** | Headless UI + 自定义组件 | 无样式基础组件 + 业务组件 |
| **图标** | Heroicons + Lucide React | 医疗场景图标 |
| **动画** | Framer Motion | 页面切换、对话流式动画 |
| **Mock数据** | JSON fixtures + API Routes | 模拟后端接口 |
| **AI流式输出** | EventSource (SSE) + Mock流 | 模拟OpenAI SDK流式响应 |

### 1.2 目录结构

```
frontend/
├── app/                          # Next.js App Router
│   ├── (nurse)/                  # 医护端路由组
│   │   ├── layout.tsx            # 医护端布局（侧边栏+顶栏）
│   │   ├── dashboard/            # 今日概览
│   │   ├── patients/             # 患者管理
│   │   ├── monitor/              # 实时监控
│   │   ├── quality/              # AI质量评价
│   │   └── config/               # 系统配置
│   ├── (patient)/                # 患者端路由组
│   │   ├── layout.tsx            # 患者端布局（移动优先）
│   │   ├── verify/               # 身份核验
│   │   ├── home/                 # 首页（住院指南）
│   │   ├── assistant/            # 住院AI助手
│   │   └── tasks/                # 任务列表与执行
│   ├── api/                      # API Routes (Mock后端)
│   │   ├── nurse/                # 医护端接口
│   │   └── patient/              # 患者端接口
│   └── login/                    # 登录页
├── components/                   # 可复用组件
│   ├── shared/                   # 通用组件（按钮/卡片/表单）
│   ├── chat/                     # 对话组件（气泡/输入框/流式）
│   ├── assessment/               # 评估组件（题目/进度/结果）
│   ├── task/                     # 任务组件（卡片/状态/操作）
│   └── layout/                   # 布局组件（侧边栏/顶栏/容器）
├── lib/                          # 工具库
│   ├── stores/                   # Zustand状态管理
│   ├── mock/                     # Mock数据生成器
│   ├── types/                    # TypeScript类型定义
│   └── utils/                    # 工具函数
└── public/                       # 静态资源（图标/示例图片）
```

## 2. 路由设计

### 2.1 医护端（桌面Web）

**路由前缀：** `/nurse`

| 路由 | 页面 | 功能 |
|------|------|------|
| `/nurse/login` | 登录页 | 演示账号登录 |
| `/nurse/dashboard` | 今日概览 | 待办任务、统计卡片、快捷入口 |
| `/nurse/patients` | 患者列表 | 在院患者列表 + 搜索筛选 |
| `/nurse/patients/[id]` | 患者详情 | 住院信息 + 创建任务入口 |
| `/nurse/patients/[id]/create-task` | 创建任务 | 选择量表/模式/负责人 |
| `/nurse/monitor` | 实时监控 | 进行中/待复核/需介入/已完成任务 |
| `/nurse/monitor/[taskId]` | 任务监控详情 | 对话回放 + 实时状态 |
| `/nurse/monitor/[taskId]/review` | 复核页面 | AI结果 + 护士补充 + 人机对比 |
| `/nurse/quality` | AI质量评价 | 对话质量/评估质量评分列表 |
| `/nurse/quality/[sessionId]` | 质量评价详情 | 逐轮反馈 + 维度打分 |
| `/nurse/config` | 系统配置 | 量表/宣教/知情同意书管理 |

### 2.2 患者端（移动H5）

**路由前缀：** `/patient`

| 路由 | 页面 | 功能 |
|------|------|------|
| `/patient/verify` | 身份核验 | 输入住院号+证件后四位 / 扫码 |
| `/patient/home` | 首页 | 住院宣教、注意事项、快捷服务 |
| `/patient/assistant` | 住院AI助手 | 独立对话窗口（生活指导） |
| `/patient/tasks` | 任务列表 | 待完成/已完成任务 |
| `/patient/tasks/[taskId]` | 任务详情 | 任务说明 + 开始按钮 |
| `/patient/tasks/[taskId]/form` | 传统问卷 | 逐题填写 + 自动保存 |
| `/patient/tasks/[taskId]/chat` | AI对话评估 | CICARE六阶段对话 |
| `/patient/tasks/[taskId]/consent` | 知情同意 | 条款播报 + 签名 |
| `/patient/tasks/[taskId]/complete` | 完成页面 | 提交确认 + 等待护士复核 |

## 3. 组件库设计

### 3.1 通用组件 (`components/shared/`)

| 组件 | 用途 | Props示例 |
|------|------|-----------|
| `Button` | 主按钮/次按钮/文本按钮 | `variant, size, loading, disabled` |
| `Card` | 卡片容器 | `title, actions, hoverable, bordered` |
| `Badge` | 状态徽章 | `status, text, color` |
| `Progress` | 进度条 | `current, total, label, showPercent` |
| `Tag` | 标签 | `label, color, closable` |
| `Modal` | 弹窗 | `open, title, onClose, footer` |
| `Avatar` | 头像 | `name, src, size` |
| `Skeleton` | 骨架屏 | `lines, avatar, card` |
| `Empty` | 空状态 | `description, image` |

### 3.2 对话组件 (`components/chat/`)

| 组件 | 用途 | 特性 |
|------|------|------|
| `ChatBubble` | 对话气泡 | 支持AI/患者/系统角色，流式动画 |
| `ChatInput` | 输入框 | 文字/语音切换，发送/暂停 |
| `CicareStage` | CICARE阶段指示器 | 6阶段进度显示 |
| `StructuredAnswer` | 结构化答案卡片 | 显示AI提取的答案，支持纠正 |
| `EducationCard` | 宣教卡片 | 插入对话中的宣教内容 |
| `VoiceVisualizer` | 语音可视化 | 录音/播放波形动画 |

### 3.3 评估组件 (`components/assessment/`)

| 组件 | 用途 | 特性 |
|------|------|------|
| `QuestionRenderer` | 题目渲染器 | 根据题型渲染不同输入组件 |
| `OptionGroup` | 选项组 | 单选/多选/下拉 |
| `ScoreDisplay` | 分数展示 | 总分/风险等级/颜色映射 |
| `RiskTag` | 风险标签 | 低/中/高风险视觉区分 |
| `ComparisonTable` | 人机对比表格 | AI vs 护士答案差异展示 |

### 3.4 任务组件 (`components/task/`)

| 组件 | 用途 | 特性 |
|------|------|------|
| `TaskCard` | 任务卡片 | 展示任务状态/进度/操作 |
| `TaskTimeline` | 任务时间线 | 创建/开始/完成时间流 |
| `TaskStatusBadge` | 任务状态徽章 | 待开始/进行中/待复核/已完成 |
| `PatientInfo` | 患者信息卡片 | 姓名/床号/诊断快照 |

## 4. Mock数据策略

### 4.1 数据来源

基于已完成的DDL结构（`docs/sql/ddl/*.sql`），生成符合数据库字段的Mock数据。

**核心Mock文件：**

```
frontend/lib/mock/
├── patients.ts           # 患者列表（20条）
├── scales.ts             # 量表配置（入院评估单/ADL/Braden/NRS2002）
├── tasks.ts              # 任务列表（不同状态）
├── chat-sessions.ts      # 对话会话（含CICARE阶段标记）
├── chat-messages.ts      # 对话消息（含AI/患者/系统角色）
├── assessments.ts        # 评估结果（AI提交/护士提交/最终确认）
├── education-content.ts  # 宣教内容
└── consent-docs.ts       # 知情同意书
```

### 4.2 AI流式输出模拟

**方案：** 使用Next.js API Route模拟SSE流

```typescript
// app/api/patient/chat/stream/route.ts
export async function POST(req: Request) {
  const { message, sessionId } = await req.json();
  
  const stream = new ReadableStream({
    async start(controller) {
      const mockResponse = "这是AI的回复内容...";
      for (let i = 0; i < mockResponse.length; i++) {
        controller.enqueue(`data: ${JSON.stringify({ token: mockResponse[i] })}\n\n`);
        await new Promise(r => setTimeout(r, 30)); // 30ms/字
      }
      controller.enqueue(`data: [DONE]\n\n`);
      controller.close();
    }
  });
  
  return new Response(stream, {
    headers: { 'Content-Type': 'text/event-stream' }
  });
}
```

**前端消费：**

```typescript
const eventSource = new EventSource('/api/patient/chat/stream');
eventSource.onmessage = (event) => {
  const { token } = JSON.parse(event.data);
  // 逐字追加到对话气泡
};
```

### 4.3 Mock数据更新策略

- **本地状态：** 使用Zustand管理任务/对话状态，模拟实时更新
- **持久化：** 使用`localStorage`模拟会话保存，刷新后可恢复
- **延迟模拟：** 接口返回添加100-300ms延迟，模拟真实网络

## 5. 视觉设计规范

### 5.1 色彩方案（医疗场景 + 现代化）

**主色系：**
- **背景：** 暖白 `#F7F4EF`（柔和，减少眼疲劳）
- **表面：** 白色卡片 `#FFFFFF` + 浅灰卡片 `#FBF9F5`
- **边框：** 暖色细线 `#E7E1D7`

**功能色：**
- **主色（强调）：** 赤陶橙 `#C4612F`（按钮、链接、重要标签）
- **成功/安全：** 护理绿 `#52C41A`（已完成、低风险）
- **警告：** 琥珀黄 `#FAAD14`（待处理、中风险）
- **危险：** 医疗红 `#FF4D4F`（高风险、异常）
- **信息：** 医疗蓝 `#1890FF`（通知、提示）

**文本色：**
- **主文本：** 深墨 `#1F2421`
- **次要文本：** 中灰 `#5C635D`
- **占位符：** 浅灰 `#BFBFBF`

### 5.2 字体层级

| 层级 | 场景 | 字体 | 字号 | 行高 | 字重 |
|------|------|------|------|------|------|
| H1 | 页面标题 | DM Serif Display | 32px | 40px | 500 |
| H2 | 区块标题 | DM Serif Display | 24px | 32px | 500 |
| H3 | 卡片标题 | Inter | 18px | 26px | 600 |
| Body | 正文 | Inter | 15px | 24px | 400 |
| Small | 辅助文本 | Inter | 13px | 20px | 400 |
| Caption | 说明文字 | Inter | 12px | 18px | 400 |

**特殊处理：**
- H1/H2标题中**关键词斜体**并使用terracotta色（`italic text-[#C4612F]`）
- 患者端移动H5字号整体+1px（可读性优化）

### 5.3 间距系统（8px基准）

```
spacing-1: 4px   (内边距/图标间距)
spacing-2: 8px   (元素间小间距)
spacing-3: 12px  (表单项间距)
spacing-4: 16px  (卡片内边距)
spacing-6: 24px  (区块间距)
spacing-8: 32px  (页面区块间距)
spacing-12: 48px (大区块间距)
```

### 5.4 卡片与阴影

**卡片样式：**
```css
.card {
  background: white;
  border: 1px solid #E7E1D7;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(31, 36, 33, 0.06);
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(31, 36, 33, 0.12);
  transition: all 0.2s ease;
}
```

**AI对话气泡：**
- AI气泡：白色卡片 + 左对齐 + 细边框
- 患者气泡：terracotta浅色背景 `#F2E3D6` + 右对齐 + 无边框
- 系统提示：居中 + 虚线边框 + 浅灰背景

### 5.5 图标使用

| 场景 | 图标库 | 示例 |
|------|--------|------|
| 医护端导航 | Heroicons | `UserGroupIcon`, `ClipboardDocumentListIcon` |
| 患者端底部导航 | Lucide React | `Home`, `MessageCircle`, `Bell` |
| 状态徽章 | 内置SVG | 成功✓ / 警告⚠ / 危险✕ |

## 6. 状态管理方案

### 6.1 全局状态（Zustand）

```typescript
// lib/stores/useUserStore.ts
interface UserStore {
  role: 'nurse' | 'patient' | null;
  userId: string;
  userName: string;
  department?: string;
  patientId?: string;
  encounterId?: string;
  login: (user: User) => void;
  logout: () => void;
}

// lib/stores/useTaskStore.ts
interface TaskStore {
  tasks: Task[];
  currentTask: Task | null;
  setCurrentTask: (task: Task) => void;
  updateTaskStatus: (taskId: string, status: string) => void;
}
```

### 6.2 局部状态（React Context）

```typescript
// app/(patient)/tasks/[taskId]/chat/ChatContext.tsx
interface ChatContext {
  messages: Message[];
  isStreaming: boolean;
  cicareStage: CicareStage;
  structuredAnswers: StructuredAnswer[];
  sendMessage: (content: string) => void;
  correctAnswer: (questionId: string, newValue: string) => void;
}
```

## 7. 开发阶段划分

### 阶段1：医护端核心流程（5-7天）
- [ ] 1.1 医护端布局 + 登录页
- [ ] 1.2 今日概览页面（统计卡片）
- [ ] 1.3 患者列表 + 搜索筛选
- [ ] 1.4 患者详情 + 创建任务流程（量表选择/模式选择/负责人）
- [ ] 1.5 任务监控列表（不同状态Tab）
- [ ] 1.6 任务监控详情（对话回放/实时状态）

### 阶段2：患者端AI对话（7-10天）
- [ ] 2.1 患者端布局 + 身份核验
- [ ] 2.2 首页（住院指南卡片）
- [ ] 2.3 任务列表 + 任务详情
- [ ] 2.4 AI对话页面
  - [ ] CICARE六阶段流程
  - [ ] 对话气泡流式动画
  - [ ] 结构化答案实时更新
  - [ ] 患者纠正答案交互
- [ ] 2.5 SSE流式输出Mock接口
- [ ] 2.6 语音输入/播放UI（占位+动画）

### 阶段3：护士复核流程（4-6天）
- [ ] 3.1 复核页面布局
- [ ] 3.2 AI结果展示（答案+分数+风险）
- [ ] 3.3 护士补充问诊表单
- [ ] 3.4 人机对比表格（差异高亮）
- [ ] 3.5 确认/退回/作废操作流

### 阶段4：补充功能（3-5天）
- [ ] 4.1 传统问卷模式（患者端）
- [ ] 4.2 知情同意宣讲流程
- [ ] 4.3 实时宣教卡片插入
- [ ] 4.4 AI质量评价页面
- [ ] 4.5 系统配置页面（量表/宣教管理）

### 阶段5：优化与完善（2-3天）
- [ ] 5.1 响应式适配（患者端移动H5）
- [ ] 5.2 加载骨架屏 + 错误处理
- [ ] 5.3 页面切换动画
- [ ] 5.4 细节打磨（图标/间距/颜色微调）

**预计总工期：** 21-31天（按每日6-8小时有效开发时间）

## 8. 技术约束与注意事项

### 8.1 数据一致性
- Mock数据结构必须与DDL字段一致（参考`docs/sql/ddl/*.sql`）
- 状态流转遵守业务约束（如`care_task.task_status`的有效值）

### 8.2 性能优化
- 对话消息列表使用虚拟滚动（`react-window`）
- 大量任务列表分页加载
- 图片使用Next.js `<Image>`组件优化

### 8.3 可访问性
- 按钮/链接支持键盘导航
- 表单输入提供`label`和错误提示
- 颜色对比度符合WCAG AA标准

### 8.4 安全边界
- 原型不实现真实加密（`*_ciphertext`字段显示占位符）
- 不实现真实签名（显示"演示占位"）
- Mock登录无密码校验

## 9. 交付物

### 9.1 阶段1交付
- 医护端可运行原型（登录 → 创建任务 → 监控列表）
- Mock数据文件（患者/量表/任务）
- 基础组件库（Button/Card/Badge/Progress）

### 9.2 阶段2交付
- 患者端AI对话完整流程（核验 → 对话 → 提交）
- SSE流式输出Mock接口
- 对话组件库（ChatBubble/ChatInput/CicareStage）

### 9.3 阶段3交付
- 护士复核页面（AI结果 + 人机对比）
- 评估组件库（QuestionRenderer/ComparisonTable）

### 9.4 最终交付
- 完整前端原型（医护端 + 患者端）
- 组件库文档（Storybook可选）
- Mock数据生成器
- 部署到Vercel演示

## 10. 下一步行动

**等待确认：**
1. 视觉风格是否符合预期（暖色系+serif标题+terracotta accent）？
2. 开发阶段划分是否合理（优先级：医护核心 → 患者对话 → 复核）？
3. 是否需要调整Mock数据策略或技术选型？

**确认后立即启动：**
- 初始化Next.js项目
- 配置Tailwind CSS + TypeScript
- 搭建项目目录结构
- 创建基础布局组件
- 生成第一批Mock数据

---

**方案制定完成，等待确认后开始开发。**
