"use client";

import { useEffect, useRef } from "react";

interface AudioVisualizerProps {
  isRecording: boolean;
  level: number;
}

/** Renders the numeric microphone level supplied by the local Python API. */
export function AudioVisualizer({ isRecording, level }: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const height = isRecording ? Math.max(3, Math.min(1, level) * canvas.height * 0.82) : 3;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = isRecording ? "rgba(255, 255, 255, 0.65)" : "rgba(255, 255, 255, 0.08)";
    for (let index = 0; index < 48; index += 1) {
      const width = 9;
      const x = index * 18 + 4;
      ctx.beginPath();
      ctx.roundRect(x, (canvas.height - height) / 2, width, height, 999);
      ctx.fill();
    }
  }, [isRecording, level]);

  return (
    <canvas
      ref={canvasRef}
      width={900}
      height={80}
      className="w-full h-20"
      aria-label={isRecording ? `Live microphone level ${Math.round(level * 100)} percent` : "Microphone inactive"}
    />
  );
}
