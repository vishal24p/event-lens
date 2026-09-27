"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";

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
}

const TONE: Record<ToastType, string> = {
  success: "border-[rgba(106,154,146,0.45)] bg-[rgba(106,154,146,0.14)]",
  start: "border-[rgba(197,106,58,0.45)] bg-[rgba(197,106,58,0.14)]",
  warning: "border-[rgba(196,92,74,0.45)] bg-[rgba(196,92,74,0.14)]",
  stop: "border-[rgba(197,106,58,0.45)] bg-[rgba(197,106,58,0.14)]",
  info: "border-[var(--hairline)] bg-[var(--vitrine)]",
};

export function ToastNotification({ toast }: ToastProps) {
  const reducedMotion = useReducedMotion() ?? false;

  return (
    <AnimatePresence>
      {toast ? (
        <motion.div
          key={toast.id}
          role="status"
          aria-live="polite"
          initial={reducedMotion ? false : { opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reducedMotion ? undefined : { opacity: 0, y: -6 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className={`fixed top-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-full border px-4 py-2.5 text-sm text-[var(--bone)] shadow-[0_16px_40px_rgba(0,0,0,0.35)] ${TONE[toast.type]}`}
        >
          <span className="font-medium tracking-tight">{toast.title}</span>
          {toast.description ? (
            <span className="font-mono text-xs text-[var(--muted)]">({toast.description})</span>
          ) : null}
          {toast.keyHint ? <kbd>{toast.keyHint}</kbd> : null}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
