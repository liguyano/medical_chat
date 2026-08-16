# 前端构建错误修复记录

> 日期：2026-08-16
>
> 分支：`fix/frontend-build`
>
> 影响范围：前端原型构建、患者AI对话、传统问卷、护士任务详情

## 1. 问题现象

生产构建首先报错：

```text
Module not found: Can't resolve '@/lib/stores/useDialogueStore'
```

进一步执行全量 TypeScript 检查后，共发现 85 个类型错误，涉及 7 个文件。首个模块错误修复后仍会被后续类型和预渲染错误阻塞。

## 2. 根因

1. 对话页引用不存在的 `useDialogueStore`，仓库实际实现为 `useChatStore`。
2. 对话页按扁平 `messages` 和 `setSessionId` 使用 Store，但实际 Store 以完整 `InteractionSession` 为状态根。
3. `InteractionMessage` 使用 `role`，组件和页面使用 `roleType`，消息意图和结构化答案字段也不一致。
4. `AssessmentQuestion`、`AssessmentOption`、`CareTask` 与页面 Mock 数据字段命名不一致。
5. 任务 Store 缺少创建页面调用的 `addTask`。
6. Next.js 16 动态路由参数仍按旧版同步 `params` 方式读取。
7. `/patient` 在静态预渲染页面中直接使用 `useSearchParams`，缺少 `Suspense` 边界。
8. Framer Motion 动画对象没有使用 `Variants` 上下文类型，导致 easing 被推断成普通字符串。

## 3. 修复内容

- 统一使用 `useChatStore`，在患者对话页初始化完整 `InteractionSession`。
- 统一对话消息角色、CICARE阶段、意图和结构化答案类型。
- 使用 `useParams` 读取患者对话、传统问卷、完成页和护士任务详情的动态参数。
- 为患者入口的 `useSearchParams` 增加 `Suspense` 边界。
- 统一量表题目和选项字段为 `questionCode`、`required`、`validationRule`、`optionCode`、`optionLabel` 和 `clinicalScore`。
- 补齐任务视图字段、Mock快照和任务 Store 的 `addTask`。
- 为动画配置增加 `Variants` 类型。
- 清理无效导入、空会话新增消息失效和服务端渲染期间访问 `window` 等风险。

## 4. 验证结果

以下命令全部通过：

```text
pnpm lint
pnpm exec tsc --noEmit
pnpm build
```

Next.js 16.3.1 生产构建成功生成全部静态和动态路由。

浏览器烟雾验证通过：

- 患者任务入口正常加载。
- AI对话任务可进入，欢迎消息正常显示。
- 患者发送消息后，患者消息和模拟AI回复均能追加，进度由0更新为1。
- 传统问卷页面正常显示题目与必填状态。
- 护士任务详情正常显示住院号、科室、病区和量表版本。
- 上述页面浏览器控制台无错误。
