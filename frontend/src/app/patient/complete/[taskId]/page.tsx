'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import {
  CheckCircleIcon,
  ClockIcon,
  DocumentCheckIcon,
  HomeIcon,
} from '@heroicons/react/24/outline';

interface PageProps {
  params: {
    taskId: string;
  };
}

export default function PatientCompletePage({ params }: PageProps) {
  const router = useRouter();
  const [showConfetti, setShowConfetti] = useState(true);

  useEffect(() => {
    // 5秒后隐藏庆祝动画
    const timer = setTimeout(() => setShowConfetti(false), 5000);
    return () => clearTimeout(timer);
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.5, ease: 'easeOut' },
    },
  };

  return (
    <PatientLayout title="评估完成">
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <motion.div
          className="w-full max-w-md"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          {/* 成功图标 */}
          <motion.div variants={itemVariants} className="text-center mb-6">
            <div className="relative inline-block">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{
                  type: 'spring',
                  stiffness: 200,
                  damping: 15,
                  delay: 0.1,
                }}
                className="w-24 h-24 bg-success rounded-full flex items-center justify-center mx-auto mb-4"
              >
                <CheckCircleIcon className="w-14 h-14 text-white" />
              </motion.div>

              {/* 庆祝动画效果 */}
              {showConfetti && (
                <>
                  {[...Array(8)].map((_, i) => (
                    <motion.div
                      key={i}
                      initial={{ scale: 0, x: 0, y: 0 }}
                      animate={{
                        scale: [0, 1, 1],
                        x: [0, Math.cos((i * Math.PI) / 4) * 60],
                        y: [0, Math.sin((i * Math.PI) / 4) * 60],
                        opacity: [1, 1, 0],
                      }}
                      transition={{
                        duration: 1.5,
                        delay: 0.5,
                        ease: 'easeOut',
                      }}
                      className="absolute top-1/2 left-1/2 w-3 h-3 rounded-full"
                      style={{
                        backgroundColor: i % 2 === 0 ? '#C4612F' : '#F2E3D6',
                      }}
                    />
                  ))}
                </>
              )}
            </div>

            <motion.h1
              variants={itemVariants}
              className="text-2xl font-serif font-medium text-foreground mb-2"
            >
              评估已<span className="text-success italic">完成</span>
            </motion.h1>
            <motion.p variants={itemVariants} className="text-foreground-muted">
              感谢您的配合，评估结果已提交
            </motion.p>
          </motion.div>

          {/* 信息卡片 */}
          <motion.div variants={itemVariants}>
            <Card padding="lg" className="mb-4">
              <div className="space-y-4">
                <div className="flex items-start space-x-3">
                  <div className="p-2 bg-primary-tint rounded-lg flex-shrink-0">
                    <DocumentCheckIcon className="w-5 h-5 text-primary" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-foreground mb-1">
                      评估已提交
                    </h3>
                    <p className="text-xs text-foreground-muted leading-relaxed">
                      您的评估答案已成功提交给护士站，护士会在审核后与您确认相关信息
                    </p>
                  </div>
                </div>

                <div className="flex items-start space-x-3">
                  <div className="p-2 bg-blue-50 rounded-lg flex-shrink-0">
                    <ClockIcon className="w-5 h-5 text-info" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-foreground mb-1">
                      后续流程
                    </h3>
                    <p className="text-xs text-foreground-muted leading-relaxed">
                      护士会根据评估结果为您制定个性化的护理计划，并在必要时与您进一步沟通
                    </p>
                  </div>
                </div>

                <div className="flex items-start space-x-3">
                  <div className="p-2 bg-surface-secondary rounded-lg flex-shrink-0">
                    <HomeIcon className="w-5 h-5 text-foreground-muted" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-foreground mb-1">
                      温馨提示
                    </h3>
                    <p className="text-xs text-foreground-muted leading-relaxed">
                      如有任何疑问或身体不适，请随时按铃呼叫护士
                    </p>
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>

          {/* 操作按钮 */}
          <motion.div variants={itemVariants} className="space-y-3">
            <Button
              onClick={() => router.push('/patient')}
              className="w-full"
            >
              <HomeIcon className="w-4 h-4 mr-2" />
              返回首页
            </Button>

            <Button
              variant="outline"
              onClick={() => {
                // TODO: 查看评估详情
                console.log('查看评估详情');
              }}
              className="w-full"
            >
              查看评估记录
            </Button>
          </motion.div>

          {/* 任务编号 */}
          <motion.div variants={itemVariants} className="mt-6 text-center">
            <p className="text-xs text-foreground-muted">
              任务编号: {params.taskId}
            </p>
          </motion.div>
        </motion.div>
      </div>
    </PatientLayout>
  );
}
