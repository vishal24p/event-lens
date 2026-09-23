"use client";

import { useEffect, useRef } from "react";

interface AudioVisualizerProps {
  isRecording: boolean;
  level: number;
}

/** Camera-iris meter driven by the numeric microphone level from the local API. */
export function AudioVisualizer({ isRecording, level }: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const targetRef = useRef(0);
  const currentRef = useRef(0);
  const recordingRef = useRef(isRecording);
  const frameRef = useRef<number>(0);

  targetRef.current = isRecording ? Math.min(1, Math.max(0, level)) : 0;
  recordingRef.current = isRecording;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const paint = () => {
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = canvas.clientWidth;
      const cssHeight = canvas.clientHeight;
      const width = Math.max(1, Math.floor(cssWidth * dpr));
      const height = Math.max(1, Math.floor(cssHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      const ease = 0.14;
      currentRef.current += (targetRef.current - currentRef.current) * ease;
      const live = recordingRef.current;
      const t = currentRef.current;

      ctx.clearRect(0, 0, width, height);
      const cx = width / 2;
      const cy = height / 2;
      const radius = Math.min(width, height) * 0.42;

      ctx.strokeStyle = live ? "rgba(197, 106, 58, 0.35)" : "rgba(232, 224, 208, 0.16)";
      ctx.lineWidth = 1.5 * dpr;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();

      const blades = 8;
      const open = 0.18 + t * 0.72;
      ctx.save();
      ctx.translate(cx, cy);
      for (let i = 0; i < blades; i += 1) {
        ctx.rotate((Math.PI * 2) / blades);
        ctx.beginPath();
        ctx.fillStyle = live ? "rgba(197, 106, 58, 0.22)" : "rgba(232, 224, 208, 0.08)";
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, radius * open, -0.28, 0.28);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();

      const aperture = radius * (0.12 + t * 0.38);
      const glow = ctx.createRadialGradient(cx, cy, aperture * 0.2, cx, cy, aperture);
      glow.addColorStop(0, live ? "rgba(232, 224, 208, 0.55)" : "rgba(232, 224, 208, 0.08)");
      glow.addColorStop(1, "rgba(20, 22, 28, 0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, cy, aperture, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = live ? "rgba(243, 238, 228, 0.55)" : "rgba(232, 224, 208, 0.22)";
      ctx.lineWidth = dpr;
      ctx.beginPath();
      ctx.arc(cx, cy, aperture, 0, Math.PI * 2);
      ctx.stroke();

      frameRef.current = window.requestAnimationFrame(paint);
    };

    frameRef.current = window.requestAnimationFrame(paint);
    return () => window.cancelAnimationFrame(frameRef.current);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="size-full"
      aria-hidden="true"
    />
  );
}
