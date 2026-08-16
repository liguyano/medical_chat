'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/shared/Button';

interface SignaturePadProps {
  onChange: (dataUrl: string | undefined) => void;
}

export default function SignaturePad({ onChange }: SignaturePadProps) {
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
    const context = canvasRef.current?.getContext('2d');
    if (!context) return;
    const current = point(event);
    drawingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    context.beginPath();
    context.moveTo(current.x, current.y);
  };

  const draw = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return;
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
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    setHasSignature(false);
    onChange(undefined);
  };

  return (
    <div>
      <div className="rounded-2xl border-2 border-dashed border-border bg-surface-secondary overflow-hidden">
        <canvas
          ref={canvasRef}
          className="w-full h-40 touch-none cursor-crosshair"
          onPointerDown={start}
          onPointerMove={draw}
          onPointerUp={finish}
          onPointerCancel={finish}
          aria-label="手写签名区域"
        />
      </div>
      <div className="flex items-center justify-between mt-2">
        <p className="text-xs text-foreground-muted">
          {hasSignature ? '已记录演示签名' : '请在上方区域手写签名'}
        </p>
        <Button type="button" variant="ghost" size="sm" onClick={clear}>
          清除重签
        </Button>
      </div>
    </div>
  );
}
