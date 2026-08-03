"use client";

import { motion, AnimatePresence } from "motion/react";
import { Keyboard, X, Command } from "lucide-react";

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const shortcuts = [
  { key: "Enter", description: "Save current visitor audio and start next visitor recording", category: "Capture Actions", action: "Save & Next" },
  { key: "Esc", description: "Discard current partial audio recording and retry current visitor", category: "Capture Actions", action: "Stop & Retry" },
  { key: "Q", description: "Stop active recording safely while saved feedback keeps processing", category: "Capture Control", action: "Stop Capture" },
  { key: "?", description: "Open / close operator keyboard shortcuts guide", category: "Navigation", action: "Help Guide" },
  { key: "R", description: "Generate the final museum report after capture and transcription finish", category: "Reporting", action: "Generate Report" },
];

export function KeyboardShortcutsModal({ isOpen, onClose }: KeyboardShortcutsModalProps) {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-white/20 bg-[#0d0d0e] shadow-2xl p-6 text-white"
          role="dialog"
          aria-modal="true"
          aria-labelledby="shortcuts-title"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-lg bg-white/10 text-[#c6ff33]">
                <Keyboard className="size-5" />
              </div>
              <div>
                <h2 id="shortcuts-title" className="text-base font-semibold tracking-tight">
                  Operator Keyboard Controls
                </h2>
                <p className="text-xs text-white/50">
                  Quick keys for hands-free live museum feedback capture
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-white/60 hover:bg-white/10 hover:text-white transition-colors"
              aria-label="Close keyboard shortcuts"
            >
              <X className="size-5" />
            </button>
          </div>

          {/* Shortcut List */}
          <div className="mt-4 space-y-3 max-h-[60vh] overflow-y-auto pr-1">
            {shortcuts.map((sc, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-3 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/15 transition-colors"
              >
                <div className="flex flex-col pr-4">
                  <span className="text-sm font-medium text-white">{sc.action}</span>
                  <span className="text-xs text-white/50">{sc.description}</span>
                </div>

                <div className="shrink-0">
                  <kbd className="px-3 py-1.5 font-mono text-xs font-semibold rounded-lg bg-white/10 border border-white/20 text-[#c6ff33] shadow-sm">
                    {sc.key}
                  </kbd>
                </div>
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="mt-6 flex items-center justify-between border-t border-white/10 pt-4 text-xs text-white/50">
            <div className="flex items-center gap-1.5">
              <Command className="size-3.5 text-[#c6ff33]" />
              <span>Operator Console v0.1.0</span>
            </div>
            <span>Press <kbd className="px-1.5 py-0.5 font-mono text-[10px] rounded bg-white/10 border border-white/20">ESC</kbd> or click outside to dismiss</span>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
