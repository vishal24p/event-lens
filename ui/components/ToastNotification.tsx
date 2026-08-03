"use client";

import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, AlertTriangle, Square, Play, Info } from "lucide-react";

export type ToastType = "success" | "warning" | "stop" | "start" | "info";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  keyHint?: string;
}

interface ToastProps {
  toast: ToastMessage | null;
  onDismiss?: () => void;
}

export function ToastNotification({ toast }: ToastProps) {
  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          key={toast.id}
          initial={{ opacity: 0, y: -20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.95 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
          className="fixed top-5 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-3 rounded-full border shadow-2xl backdrop-blur-md"
          style={{
            backgroundColor:
              toast.type === "success"
                ? "rgba(198, 255, 51, 0.12)"
                : toast.type === "warning"
                ? "rgba(216, 77, 77, 0.15)"
                : toast.type === "stop"
                ? "rgba(255, 170, 0, 0.15)"
                : "rgba(255, 255, 255, 0.10)",
            borderColor:
              toast.type === "success"
                ? "rgba(198, 255, 51, 0.4)"
                : toast.type === "warning"
                ? "rgba(216, 77, 77, 0.4)"
                : toast.type === "stop"
                ? "rgba(255, 170, 0, 0.4)"
                : "rgba(255, 255, 255, 0.2)",
            color: "#ffffff",
          }}
          role="status"
          aria-live="polite"
        >
          <div className="flex items-center justify-center size-6 rounded-full shrink-0">
            {toast.type === "success" && <CheckCircle2 className="size-5 text-[#c6ff33]" />}
            {toast.type === "warning" && <AlertTriangle className="size-5 text-[#d84d4d]" />}
            {toast.type === "stop" && <Square className="size-4 text-[#ffaa00]" />}
            {toast.type === "start" && <Play className="size-4 text-[#c6ff33]" />}
            {toast.type === "info" && <Info className="size-5 text-white/80" />}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm font-medium tracking-tight text-white">{toast.title}</span>
            {toast.description && (
              <span className="text-xs text-white/60 font-mono">({toast.description})</span>
            )}
          </div>

          {toast.keyHint && (
            <kbd className="ml-1.5 px-2 py-0.5 text-[10px] font-mono rounded bg-white/10 border border-white/20 text-white/80">
              {toast.keyHint}
            </kbd>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
