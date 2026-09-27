"use client";

import { useEffect, useId, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const shortcuts = [
  { key: "Enter", action: "Start, or keep & next", detail: "Opens the booth, or saves this visitor and starts the next take." },
  { key: "Esc", action: "Discard take", detail: "Throws away the current partial recording and retries this visitor ID." },
  { key: "Q", action: "Close booth", detail: "Stops capture for this run. Saved takes keep processing." },
  { key: "R", action: "Write report", detail: "Available after the booth is closed and the ledger has finished." },
  { key: "?", action: "This guide", detail: "Show or hide keyboard controls." },
];

export function KeyboardShortcutsModal({ isOpen, onClose }: KeyboardShortcutsModalProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const reducedMotion = useReducedMotion() ?? false;

  useEffect(() => {
    if (!isOpen) return;
    const previous = document.activeElement;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
          <motion.div
            initial={reducedMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reducedMotion ? undefined : { opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-black/70"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={reducedMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? undefined : { opacity: 0, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--hairline)] bg-[var(--vitrine)] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.45)]"
          >
            <div className="flex items-start justify-between gap-4 border-b border-[var(--hairline)] pb-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Booth</p>
                <h2 id={titleId} className="font-display mt-1 text-xl text-[var(--bone)]">
                  Hands on the keys
                </h2>
                <p className="mt-1 text-sm text-[var(--muted)] text-pretty">
                  This desk is meant to be driven without looking down.
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                className="rounded-lg px-2 py-1 text-sm text-[var(--muted)] hover:bg-white/5 hover:text-[var(--bone)]"
              >
                Close
              </button>
            </div>

            <ul className="mt-4 space-y-2">
              {shortcuts.map((row) => (
                <li
                  key={row.key}
                  className="flex items-start justify-between gap-4 rounded-xl border border-[var(--hairline)] px-3 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-[var(--bone)]">{row.action}</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-[var(--muted)] text-pretty">{row.detail}</p>
                  </div>
                  <kbd className="mt-0.5 shrink-0">{row.key}</kbd>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-[var(--muted)]">
              Keep & rest has no key — it saves this visitor and leaves the booth idle.
            </p>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  );
}
