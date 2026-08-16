# 前端构建错误修复计划

> 修复日期：2026-08-16
>
> 修复分支：`fix/frontend-build`
>
> 目标：修复前端原型现有模块解析、类型契约和 Next.js 16 兼容问题，使 `lint`、TypeScript 检查和生产构建全部通过。

## 1. 问题分析

- [X] 1.1 确认 `useDialogueStore` 文件不存在，实际仅有 `useChatStore`
- [X] 1.2 确认对话页面、Store 和 `InteractionMessage` 类型存在接口漂移
- [X] 1.3 核对 Next.js 16 动态路由参数规范
- [X] 1.4 执行全量 TypeScript 检查并统计构建阻塞
- [X] 1.5 确认当前共有 85 个类型错误，涉及 7 个文件

## 2. 对话模块修复

- [X] 2.1 统一使用 `useChatStore` 作为对话状态入口
- [X] 2.2 正确初始化 `InteractionSession`，避免空会话时新增消息失效
- [X] 2.3 统一消息角色、意图和结构化答案字段
- [X] 2.4 修复 `ChatBubble` 与消息类型不一致问题
- [X] 2.5 按 Next.js 16 规范读取动态路由参数

## 3. 任务与问卷模块修复

- [X] 3.1 补齐 `CareTask` 页面所需字段并统一 Mock 数据
- [X] 3.2 补齐任务 Store 的新增任务能力
- [X] 3.3 统一评估题目、选项、校验与条件逻辑字段
- [X] 3.4 修复传统问卷页面和 `QuestionCard` 类型错误

## 4. 动画与框架兼容修复

- [X] 4.1 修复 Framer Motion `Variants` 的 easing 类型
- [X] 4.2 检查所有动态路由页面的 Next.js 16 参数读取方式
- [X] 4.3 清理无效导入和明显的运行时风险

## 5. 测试与复查

- [X] 5.1 执行 ESLint
- [X] 5.2 执行 TypeScript `tsc --noEmit`
- [X] 5.3 执行 Next.js 生产构建
- [X] 5.4 检查 Git 差异和工作区状态
- [X] 5.5 编写修复记录并更新本计划完成状态
