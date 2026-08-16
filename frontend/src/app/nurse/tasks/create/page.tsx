'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Input } from '@/components/shared/Input';
import { Badge } from '@/components/shared/Badge';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type { CareTask } from '@/lib/types';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';

export default function CreateTaskPage() {
  const router = useRouter();
  const { addTask } = useTaskStore();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    patientName: '',
    gender: 'male' as 'male' | 'female',
    age: '',
    bedNo: '',
    inpatientNo: '',
    diagnosis: '',
    taskType: '入院评估',
    collectionMode: 'ai_dialogue' as 'ai_dialogue' | 'traditional_form',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    // 模拟创建延迟
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // 创建新任务
    const newTask: CareTask = {
      id: `T${Date.now()}`,
      taskNo: `TASK-${Date.now()}`,
      patientId: `P${Date.now()}`,
      patientName: formData.patientName,
      encounterId: `E${Date.now()}`,
      encounterNo: formData.inpatientNo,
      parentTaskId: '',
      taskType: formData.taskType,
      collectionMode: formData.collectionMode,
      taskStatus: 'pending',
      assignedNurseId: 'N001',
      assignedNurseName: '李护士',
      scaleId: 'S001',
      scaleName: '入院评估量表',
      scaleVersion: 'v1.0',
      bedNo: formData.bedNo,
      department: '心内科',
      wardName: '心内一病区',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    addTask(newTask);
    router.push(`/nurse/tasks/${newTask.id}`);
  };

  return (
    <NurseLayout>
      <div className="max-w-3xl mx-auto">
        {/* 返回按钮 */}
        <button
          onClick={() => router.back()}
          className="flex items-center space-x-2 text-foreground-muted hover:text-foreground transition-colors mb-6"
        >
          <ArrowLeftIcon className="w-5 h-5" />
          <span>返回</span>
        </button>

        {/* 页面标题 */}
        <div className="mb-6">
          <h1 className="text-3xl font-serif font-medium text-foreground mb-2">
            创建<span className="text-primary italic">护理任务</span>
          </h1>
          <p className="text-foreground-muted">为患者创建新的护理评估任务</p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* 患者信息 */}
          <Card padding="lg" className="mb-6">
            <CardHeader>
              <CardTitle>患者信息</CardTitle>
              <CardDescription>请填写患者基本信息</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input
                  label="患者姓名"
                  value={formData.patientName}
                  onChange={(e) => setFormData({ ...formData, patientName: e.target.value })}
                  required
                />
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1.5">性别</label>
                  <div className="flex space-x-4">
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, gender: 'male' })}
                      className={`flex-1 px-4 py-2.5 rounded-xl border transition-all duration-200 ${
                        formData.gender === 'male'
                          ? 'border-primary bg-primary-tint text-primary'
                          : 'border-border bg-surface hover:border-foreground-muted'
                      }`}
                    >
                      男
                    </button>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, gender: 'female' })}
                      className={`flex-1 px-4 py-2.5 rounded-xl border transition-all duration-200 ${
                        formData.gender === 'female'
                          ? 'border-primary bg-primary-tint text-primary'
                          : 'border-border bg-surface hover:border-foreground-muted'
                      }`}
                    >
                      女
                    </button>
                  </div>
                </div>
                <Input
                  label="年龄"
                  type="number"
                  value={formData.age}
                  onChange={(e) => setFormData({ ...formData, age: e.target.value })}
                  required
                />
                <Input
                  label="床号"
                  value={formData.bedNo}
                  onChange={(e) => setFormData({ ...formData, bedNo: e.target.value })}
                  placeholder="如: 01床"
                  required
                />
                <Input
                  label="住院号"
                  value={formData.inpatientNo}
                  onChange={(e) => setFormData({ ...formData, inpatientNo: e.target.value })}
                  required
                />
                <Input
                  label="诊断"
                  value={formData.diagnosis}
                  onChange={(e) => setFormData({ ...formData, diagnosis: e.target.value })}
                  placeholder="主要诊断"
                  required
                />
              </div>
            </CardContent>
          </Card>

          {/* 任务配置 */}
          <Card padding="lg" className="mb-6">
            <CardHeader>
              <CardTitle>任务配置</CardTitle>
              <CardDescription>选择评估方式和量表</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-3">
                    采集方式
                  </label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, collectionMode: 'ai_dialogue' })}
                      className={`p-6 rounded-xl border-2 transition-all duration-200 text-left ${
                        formData.collectionMode === 'ai_dialogue'
                          ? 'border-primary bg-primary-tint'
                          : 'border-border bg-surface hover:border-foreground-muted'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="text-2xl">🤖</div>
                        {formData.collectionMode === 'ai_dialogue' && (
                          <Badge variant="primary" size="sm">
                            已选择
                          </Badge>
                        )}
                      </div>
                      <div className="font-medium text-foreground mb-1">AI 对话采集</div>
                      <div className="text-sm text-foreground-muted">
                        通过智能对话引导患者完成评估
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        setFormData({ ...formData, collectionMode: 'traditional_form' })
                      }
                      className={`p-6 rounded-xl border-2 transition-all duration-200 text-left ${
                        formData.collectionMode === 'traditional_form'
                          ? 'border-primary bg-primary-tint'
                          : 'border-border bg-surface hover:border-foreground-muted'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="text-2xl">📝</div>
                        {formData.collectionMode === 'traditional_form' && (
                          <Badge variant="primary" size="sm">
                            已选择
                          </Badge>
                        )}
                      </div>
                      <div className="font-medium text-foreground mb-1">传统表单</div>
                      <div className="text-sm text-foreground-muted">
                        使用传统量表表单直接填写
                      </div>
                    </button>
                  </div>
                </div>

                <Input
                  label="任务类型"
                  value={formData.taskType}
                  onChange={(e) => setFormData({ ...formData, taskType: e.target.value })}
                  disabled
                />
              </div>
            </CardContent>
          </Card>

          {/* 提交按钮 */}
          <div className="flex items-center justify-end space-x-4">
            <Button variant="outline" onClick={() => router.back()} type="button">
              取消
            </Button>
            <Button type="submit" loading={loading}>
              创建任务
            </Button>
          </div>
        </form>
      </div>
    </NurseLayout>
  );
}
