'use client';

import { motion, type Variants } from 'framer-motion';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import type { AssessmentQuestion } from '@/lib/types';
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';

type AnswerValue = string | string[] | number | boolean | null;

interface QuestionCardProps {
  question: AssessmentQuestion;
  value?: AnswerValue;
  onChange: (value: AnswerValue) => void;
  error?: string;
  animate?: boolean;
}

export default function QuestionCard({
  question,
  value,
  onChange,
  error,
  animate = true,
}: QuestionCardProps) {
  const inputValue =
    typeof value === 'string' || typeof value === 'number' ? value : '';

  const cardVariants: Variants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.3, ease: 'easeOut' },
    },
  };

  const renderInput = () => {
    if (question.derived) {
      return (
        <div className="rounded-xl border border-dashed border-border bg-surface-secondary px-4 py-3 text-sm text-foreground-muted">
          此项由系统根据前序答案计算，提交后自动生成
        </div>
      );
    }
    switch (question.questionType) {
      case 'single_choice':
        return (
          <div className="space-y-2">
            {question.options?.map((option) => (
              <button
                key={option.id ?? option.optionCode}
                type="button"
                onClick={() => onChange(option.optionCode)}
                className={`w-full p-4 rounded-xl border-2 transition-all duration-200 text-left ${
                  value === option.optionCode
                    ? 'border-primary bg-primary-tint'
                    : 'border-border bg-surface hover:border-foreground-muted'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3">
                      <div
                        className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                          value === option.optionCode
                            ? 'border-primary bg-primary'
                            : 'border-border'
                        }`}
                      >
                        {value === option.optionCode && (
                          <div className="w-2.5 h-2.5 bg-white rounded-full" />
                        )}
                      </div>
                      <span className="text-sm font-medium text-foreground">
                        {option.optionLabel}
                      </span>
                    </div>
                    {option.description && (
                      <p className="text-xs text-foreground-muted mt-2 ml-8">
                        {option.description}
                      </p>
                    )}
                  </div>
                  {option.clinicalScore !== undefined && (
                    <Badge variant="default" size="sm">
                      {option.clinicalScore} 分
                    </Badge>
                  )}
                </div>
              </button>
            ))}
          </div>
        );

      case 'multiple_choice':
        const selectedValues = Array.isArray(value) ? value : [];
        return (
          <div className="space-y-2">
            {question.options?.map((option) => {
              const isSelected = selectedValues.includes(option.optionCode);
              return (
                <button
                  key={option.id ?? option.optionCode}
                  type="button"
                  onClick={() => {
                    const newValues = isSelected
                      ? selectedValues.filter((v) => v !== option.optionCode)
                      : [...selectedValues, option.optionCode];
                    onChange(newValues);
                  }}
                  className={`w-full p-4 rounded-xl border-2 transition-all duration-200 text-left ${
                    isSelected
                      ? 'border-primary bg-primary-tint'
                      : 'border-border bg-surface hover:border-foreground-muted'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <div
                          className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
                            isSelected
                              ? 'border-primary bg-primary'
                              : 'border-border'
                          }`}
                        >
                          {isSelected && (
                            <CheckCircleIcon className="w-4 h-4 text-white" />
                          )}
                        </div>
                        <span className="text-sm font-medium text-foreground">
                          {option.optionLabel}
                        </span>
                      </div>
                      {option.description && (
                        <p className="text-xs text-foreground-muted mt-2 ml-8">
                          {option.description}
                        </p>
                      )}
                    </div>
                    {option.clinicalScore !== undefined && (
                      <Badge variant="default" size="sm">
                        {option.clinicalScore} 分
                      </Badge>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        );

      case 'text':
        return (
          <textarea
            value={inputValue}
            onChange={(e) => onChange(e.target.value)}
            placeholder={question.placeholder || '请输入您的回答...'}
            rows={4}
            className="w-full px-4 py-3 rounded-xl border border-border bg-surface resize-none
              text-foreground placeholder:text-foreground-placeholder
              focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
              transition-all duration-200"
          />
        );

      case 'number':
        return (
          <div className="flex items-center space-x-4">
            <input
              type="number"
              value={inputValue}
              onChange={(e) => onChange(e.target.value)}
              placeholder={question.placeholder || '请输入数值'}
              min={question.validationRule?.min}
              max={question.validationRule?.max}
              className="flex-1 px-4 py-3 rounded-xl border border-border bg-surface
                text-foreground placeholder:text-foreground-placeholder
                focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
                transition-all duration-200"
            />
            {question.unit && (
              <span className="text-sm text-foreground-muted">{question.unit}</span>
            )}
          </div>
        );

      case 'date':
        return (
          <input
            type="date"
            value={inputValue}
            onChange={(e) => onChange(e.target.value)}
            className="w-full px-4 py-3 rounded-xl border border-border bg-surface
              text-foreground
              focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
              transition-all duration-200"
          />
        );

      case 'boolean':
        return (
          <div className="grid grid-cols-2 gap-3">
            {[
              { value: true, label: '是' },
              { value: false, label: '否' },
            ].map((option) => (
              <button
                key={option.label}
                type="button"
                onClick={() => onChange(option.value)}
                className={`rounded-xl border-2 px-4 py-3 text-left ${
                  value === option.value
                    ? 'border-primary bg-primary-tint'
                    : 'border-border bg-surface'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        );

      default:
        return null;
    }
  };

  const CardContent = (
    <Card padding="lg" className={error ? 'border-2 border-danger' : ''}>
      {/* 题目编码仅用于接口和审计，不向用户展示；必填标记与题目同行，避免顶部产生空白区域 */}
      <div className="flex items-start gap-3 mb-4">
        <h3 className="min-w-0 flex-1 text-base font-medium text-foreground leading-relaxed">
          {question.questionText}
        </h3>
        {question.required && (
          <Badge variant="danger" size="sm">
            必填
          </Badge>
        )}
      </div>

      {/* 题目描述 */}
      {question.description && (
        <p className="text-sm text-foreground-muted mb-4 leading-relaxed">
          {question.description}
        </p>
      )}

      {/* 输入控件 */}
      <div className="mb-2">{renderInput()}</div>

      {/* 错误提示 */}
      {error && (
        <div className="flex items-center space-x-2 text-danger mt-3">
          <ExclamationCircleIcon className="w-4 h-4 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}
    </Card>
  );

  if (animate) {
    return (
      <motion.div initial="hidden" animate="visible" variants={cardVariants}>
        {CardContent}
      </motion.div>
    );
  }

  return CardContent;
}
