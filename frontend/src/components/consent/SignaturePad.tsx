'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/shared/Button';

interface SignaturePadProps {
  onChange: (dataUrl: string | undefined) => void;
  disabled?: boolean;
}

export default function SignaturePad({
  onChange,
  disabled = false,
}: SignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);
  const [hasSignature, setHasSignature] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext('2d');
    context?.scale(ratio, ratio);
    if (context) {
      context.lineWidth = 2.5;
      context.lineCap = 'round';
      context.strokeStyle = '#1F2421';
    }
  }, []);

  const point = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  };

  const start = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled) return;
    const context = canvasRef.current?.getContext('2d');
    if (!context) return;
    const current = point(event);
    drawingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    context.beginPath();
    context.moveTo(current.x, current.y);
  };

  const draw = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled || !drawingRef.current) return;
    const context = canvasRef.current?.getContext('2d');
    if (!context) return;
    const current = point(event);
    context.lineTo(current.x, current.y);
    context.stroke();
    setHasSignature(true);
  };

  const finish = () => {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    const dataUrl = canvasRef.current?.toDataURL('image/png');
    onChange(dataUrl);
  };

  const clear = () => {
    if (disabled) return;
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    setHasSignature(false);
    onChange(undefined);
  };

  return (
    <div>
      <div className="relative overflow-hidden rounded-[18px] border-2 border-[#ded6d0] bg-[#fffdfb]">
        <canvas
          ref={canvasRef}
          className={`h-32 w-full touch-none ${
            disabled ? 'cursor-not-allowed opacity-45' : 'cursor-crosshair'
          }`}
          onPointerDown={start}
          onPointerMove={draw}
          onPointerUp={finish}
          onPointerCancel={finish}
          aria-label="手写签名区域"
          aria-disabled={disabled}
        />
        {!hasSignature && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center gap-2 text-[#aaa19b]">
            <span className="text-2xl">✎</span>
            <span>{disabled ? '完成条款确认后签名' : '请在此处签名'}</span>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between mt-2">
        <p className="text-xs text-foreground-muted">
          {hasSignature
            ? '已记录演示签名'
            : disabled
              ? '签名将在全部条款确认后开放'
              : '签名可在提交前随时修改'}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={clear}
          disabled={disabled || !hasSignature}
        >
          清除重签
        </Button>
      </div>
    </div>
  );
}
