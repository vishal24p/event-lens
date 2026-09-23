"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, CornerDownLeft, FileText, Keyboard, Mic, Pause, RotateCcw, Square } from "lucide-react";

import { AudioVisualizer } from "../components/AudioVisualizer";
import { KeyboardShortcutsModal } from "../components/KeyboardShortcutsModal";
import { QueueLedger, type QueueSnapshot } from "../components/QueueLedger";
import { ToastNotification, type ToastMessage } from "../components/ToastNotification";

type OperatorStatus = {
  capture_state: "recording" | "stopped" | "idle";
  current_visitor_id: string | null;
  elapsed_seconds: number;
  input_level: number;
  report_ready: boolean;
  queue?: QueueSnapshot;
};

function formatTime(seconds: number) {
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}

export default function Home() {
  const [status, setStatus] = useState<OperatorStatus | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [pressedKey, setPressedKey] = useState<string | null>(null);
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const isRecording = status?.capture_state === "recording";
  const isIdle = status?.capture_state === "idle";
  const isStopped = status?.capture_state === "stopped";

  const showToast = useCallback((message: Omit<ToastMessage, "id">) => {
    setToast({ ...message, id: Date.now().toString() });
    window.setTimeout(() => setToast(null), 2200);
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message ?? "Unable to read booth status.");
      setStatus(payload.data);
      setConnectionError(null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : "The capture engine is not reachable.");
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    const timer = window.setInterval(() => void refreshStatus(), 500);
    return () => window.clearInterval(timer);
  }, [refreshStatus]);

  const runCaptureAction = useCallback(
    async (path: string, success: string, keyHint: string, type: ToastMessage["type"]) => {
      setBusy(path);
      try {
        const response = await fetch(path, { method: "POST" });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error?.message ?? "Action failed.");
        setStatus(payload.data);
        showToast({ type, title: success, keyHint });
      } catch (error) {
        showToast({ type: "warning", title: error instanceof Error ? error.message : "Action failed." });
      } finally {
        setBusy(null);
      }
    },
    [showToast],
  );

  const generateReport = useCallback(async () => {
    setBusy("/api/report");
    try {
      const response = await fetch("/api/report", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message ?? "Report generation failed.");
      setReportUrl(payload.data.markdown_url);
      showToast({ type: "success", title: "Report written", keyHint: "R" });
    } catch (error) {
      showToast({ type: "warning", title: error instanceof Error ? error.message : "Report generation failed." });
    } finally {
      setBusy(null);
    }
  }, [showToast]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === "?" ) {
        event.preventDefault();
        setIsShortcutsOpen((open) => !open);
        return;
      }
      if (isShortcutsOpen) return;
      const action =
        event.key === "Enter" && isIdle
          ? (["Enter", "/api/capture/start", "Listening", "start"] as const)
          : event.key === "Enter"
            ? (["Enter", "/api/capture/accept", "Visitor kept", "success"] as const)
            : event.key === "Escape"
              ? (["Escape", "/api/capture/discard", "Take discarded", "warning"] as const)
              : event.key.toLowerCase() === "q"
                ? (["Q", "/api/capture/stop", "Booth closed", "stop"] as const)
                : null;
      if (action) {
        event.preventDefault();
        setPressedKey(action[0]);
        void runCaptureAction(action[1], action[2], action[0], action[3]);
        window.setTimeout(() => setPressedKey(null), 160);
      } else if (event.key.toLowerCase() === "r" && status?.report_ready) {
        event.preventDefault();
        void generateReport();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [generateReport, isIdle, isShortcutsOpen, runCaptureAction, status?.report_ready]);

  const headline = useMemo(() => {
    if (isRecording) return "Listening";
    if (isIdle) return "Booth open";
    if (isStopped) return "Booth closed";
    return "Connecting";
  }, [isIdle, isRecording, isStopped]);

  const visitorLabel = status?.current_visitor_id ?? (isIdle ? "Next visitor" : isStopped ? "Capture ended" : "—");

  return (
    <main className="booth-shell flex min-h-svh flex-col text-[var(--bone)]">
      <ToastNotification toast={toast} />
      <KeyboardShortcutsModal isOpen={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} />

      <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-[var(--hairline)] px-4 sm:px-6">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">AI Museum · KIT</p>
          <h1 className="font-display truncate text-lg leading-tight sm:text-xl">Event Lens</h1>
        </div>
        <div className="flex items-center gap-1 sm:gap-2">
          {reportUrl ? (
            <a href={reportUrl} target="_blank" rel="noreferrer" className="px-2 py-1.5 text-xs text-[var(--celadon)] hover:underline">
              Open report
            </a>
          ) : null}
          <button
            type="button"
            onClick={() => void generateReport()}
            disabled={!status?.report_ready || busy !== null}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-[var(--muted)] hover:bg-white/5 hover:text-[var(--bone)] disabled:pointer-events-none disabled:opacity-30"
          >
            <FileText className="size-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">{busy === "/api/report" ? "Writing…" : "Report"}</span>
            <kbd>R</kbd>
          </button>
          <button
            type="button"
            onClick={() => setIsShortcutsOpen(true)}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-[var(--muted)] hover:bg-white/5 hover:text-[var(--bone)]"
          >
            <Keyboard className="size-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Keys</span>
            <kbd>?</kbd>
          </button>
        </div>
      </header>

      {connectionError ? (
        <p role="alert" className="border-b border-[rgba(196,92,74,0.35)] bg-[rgba(196,92,74,0.12)] px-4 py-2 text-sm text-[var(--bone)] sm:px-6">
          Engine unavailable: {connectionError}. Start the operator server on port 8765.
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.85fr)]">
        <section id="booth-main" className="flex min-h-0 flex-col px-4 py-5 sm:px-8 sm:py-6" aria-label="Listening booth">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Now</p>
              <p className="font-display text-3xl text-[var(--bone)] sm:text-4xl" aria-live="polite">
                {headline}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Accession</p>
              <p className="font-mono text-sm tabular-nums text-[var(--paper)]">{visitorLabel}</p>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col items-center justify-center py-6">
            <div
              className={`lens-ring relative aspect-square w-[min(100%,280px)] overflow-hidden rounded-full bg-[var(--vitrine)] sm:w-[min(100%,340px)] ${isRecording ? "is-live" : ""}`}
              role="img"
              aria-label={
                isRecording
                  ? `Live microphone, ${Math.round((status?.input_level ?? 0) * 100)} percent`
                  : "Microphone idle"
              }
            >
              <AudioVisualizer isRecording={Boolean(isRecording)} level={status?.input_level ?? 0} />
            </div>
            <p
              className="timer-nums mt-6 text-[clamp(3.25rem,8vw,5.5rem)] font-normal leading-none tracking-[-0.04em] text-[var(--paper)]"
              aria-label={`${status?.elapsed_seconds ?? 0} seconds recorded`}
            >
              {formatTime(status?.elapsed_seconds ?? 0)}
            </p>
            <p className="mt-3 max-w-md text-center text-sm text-[var(--muted)] text-pretty">
              {isRecording
                ? "Visitor is on the mic. Keep this take, discard it, or rest the booth."
                : isIdle
                  ? "Press Enter to open the lens and start the next visitor."
                  : isStopped
                    ? "This run cannot restart. Wait for the ledger, then write the report."
                    : "Waiting for the capture engine."}
            </p>
          </div>

          <div className="grid shrink-0 gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-label="Booth controls">
            <button
              type="button"
              className={`ctrl ctrl-primary ${pressedKey === "Enter" ? "is-pressed" : ""} sm:col-span-2 lg:col-span-1`}
              disabled={(!isRecording && !isIdle) || busy !== null}
              onClick={() =>
                void runCaptureAction(
                  isIdle ? "/api/capture/start" : "/api/capture/accept",
                  isIdle ? "Listening" : "Visitor kept",
                  "Enter",
                  isIdle ? "start" : "success",
                )
              }
            >
              <span className="flex items-center gap-2">
                {isIdle ? <Mic className="size-4" aria-hidden="true" /> : <Check className="size-4" aria-hidden="true" />}
                <span className="text-sm">{isIdle ? "Start listening" : "Keep & next"}</span>
              </span>
              <span className="flex items-center gap-1 font-mono text-[11px] opacity-70">
                Enter
                <CornerDownLeft className="size-3" aria-hidden="true" />
              </span>
            </button>
            <button
              type="button"
              className="ctrl ctrl-ghost"
              disabled={!isRecording || busy !== null}
              onClick={() =>
                void runCaptureAction("/api/capture/accept-and-pause", "Kept, booth idle", "", "info")
              }
            >
              <span className="flex items-center gap-2">
                <Pause className="size-4" aria-hidden="true" />
                <span className="text-sm">Keep & rest</span>
              </span>
            </button>
            <button
              type="button"
              className={`ctrl ctrl-copper ${pressedKey === "Escape" ? "is-pressed" : ""}`}
              disabled={!isRecording || busy !== null}
              onClick={() => void runCaptureAction("/api/capture/discard", "Take discarded", "Esc", "warning")}
            >
              <span className="flex items-center gap-2">
                <RotateCcw className="size-4" aria-hidden="true" />
                <span className="text-sm">Discard take</span>
              </span>
              <kbd>Esc</kbd>
            </button>
            <button
              type="button"
              className={`ctrl ctrl-warn ${pressedKey === "Q" ? "is-pressed" : ""}`}
              disabled={!isRecording || busy !== null}
              onClick={() => void runCaptureAction("/api/capture/stop", "Booth closed", "Q", "stop")}
            >
              <span className="flex items-center gap-2">
                <Square className="size-3.5 fill-current" aria-hidden="true" />
                <span className="text-sm">Close booth</span>
              </span>
              <kbd>Q</kbd>
            </button>
          </div>
        </section>

        <QueueLedger queue={status?.queue} />
      </div>
    </main>
  );
}
