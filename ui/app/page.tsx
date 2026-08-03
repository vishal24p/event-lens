"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Button, Chip } from "@heroui/react";
import { Check, CornerDownLeft, FileText, Keyboard, Mic, Radio, RotateCcw, Square } from "lucide-react";

import { AudioVisualizer } from "../components/AudioVisualizer";
import { KeyboardShortcutsModal } from "../components/KeyboardShortcutsModal";
import { ToastNotification, type ToastMessage } from "../components/ToastNotification";

type OperatorStatus = {
  capture_state: "recording" | "stopped" | "idle";
  current_visitor_id: string | null;
  elapsed_seconds: number;
  input_level: number;
  report_ready: boolean;
};

function formatTime(seconds: number) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}

export default function Home() {
  const [status, setStatus] = useState<OperatorStatus | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [pressedKey, setPressedKey] = useState<string | null>(null);
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const reducedMotion = useReducedMotion() ?? false;
  const isRecording = status?.capture_state === "recording";
  const isIdle = status?.capture_state === "idle";

  const showToast = useCallback((message: Omit<ToastMessage, "id">) => {
    setToast({ ...message, id: Date.now().toString() });
    window.setTimeout(() => setToast(null), 2200);
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/status", { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message ?? "Unable to read operator status.");
      setStatus(payload.data);
      setConnectionError(null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : "Operator backend is unavailable.");
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    const timer = window.setInterval(() => void refreshStatus(), 500);
    return () => window.clearInterval(timer);
  }, [refreshStatus]);

  const runCaptureAction = useCallback(async (path: string, success: string, keyHint: string, type: ToastMessage["type"]) => {
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
  }, [showToast]);

  const generateReport = useCallback(async () => {
    setBusy("/api/report");
    try {
      const response = await fetch("/api/report", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message ?? "Report generation failed.");
      setReportUrl(payload.data.markdown_url);
      showToast({ type: "success", title: "Museum report generated", keyHint: "R" });
    } catch (error) {
      showToast({ type: "warning", title: error instanceof Error ? error.message : "Report generation failed." });
    } finally {
      setBusy(null);
    }
  }, [showToast]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === "Escape" && isShortcutsOpen) {
        event.preventDefault();
        setIsShortcutsOpen(false);
        return;
      }
      const action = event.key === "Enter" && isIdle ? ["Enter", "/api/capture/start", "Recording started", "success"] as const
        : event.key === "Enter" ? ["Enter", "/api/capture/accept", "Visitor saved", "success"] as const
        : event.key === "Escape" ? ["Escape", "/api/capture/discard", "Recording discarded", "warning"] as const
        : event.key.toLowerCase() === "q" ? ["Q", "/api/capture/stop", "Capture stopped", "stop"] as const
        : null;
      if (action) {
        event.preventDefault();
        setPressedKey(action[0]);
        void runCaptureAction(action[1], action[2], action[0], action[3]);
        window.setTimeout(() => setPressedKey(null), 200);
      } else if (event.key.toLowerCase() === "r" && status?.report_ready) {
        event.preventDefault();
        void generateReport();
      } else if (event.key === "?") {
        event.preventDefault();
        setIsShortcutsOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [generateReport, isIdle, runCaptureAction, status?.report_ready]);

  return (
    <main className="min-h-svh h-svh overflow-hidden bg-[#060608] text-white flex flex-col relative selection:bg-[#c6ff33] selection:text-black">
      <ToastNotification toast={toast} />
      <KeyboardShortcutsModal isOpen={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} />
      <div className="relative z-10 mx-auto flex h-full w-full flex-col px-4 sm:px-8 lg:px-12 max-w-7xl">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/[0.08]">
          <div className="flex items-center gap-3">
            <div className="grid size-7 place-items-center rounded-md bg-[#c6ff33]"><Radio className="size-3.5 text-black" /></div>
            <div><h1 className="text-sm font-semibold tracking-tight text-white leading-none">Event Lens</h1><p className="text-[10px] text-white/40 mt-0.5 leading-none">Operator console</p></div>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-white/55">{status ? "Global feedback queue" : "Connecting…"}</span>
            {reportUrl && <a href={reportUrl} target="_blank" rel="noreferrer" className="text-xs text-[#c6ff33] hover:underline">Open report</a>}
            <button type="button" onClick={() => void generateReport()} disabled={!status?.report_ready || busy !== null} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-white/55 hover:text-white hover:bg-white/[0.06] disabled:opacity-30 disabled:pointer-events-none"><FileText className="size-3.5" /><span className="hidden sm:inline">Report</span><kbd>R</kbd></button>
            <button type="button" onClick={() => setIsShortcutsOpen(true)} className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-white/55 hover:text-white hover:bg-white/[0.06]"><Keyboard className="size-3.5" /><span className="hidden sm:inline">Help</span><kbd>?</kbd></button>
          </div>
        </header>

        <motion.section initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reducedMotion ? 0 : 0.25 }} className="flex min-h-0 flex-1 py-4 sm:py-5" aria-label="Feedback recording controls">
          <div className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-white/[0.10] bg-[#0c0c0f]">
            <div className="flex items-center justify-between border-b border-white/[0.07] px-6 py-3.5 sm:px-8">
              <div className="flex items-center gap-3"><Mic className={`size-4 ${isRecording ? "text-emerald-400" : "text-white/25"}`} /><div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/35 leading-none">Active visitor</p><p className="font-mono text-sm font-semibold text-white mt-1 leading-none tabular-nums">{status?.current_visitor_id ?? (isIdle ? "Ready to record" : "Capture stopped")}</p></div></div>
              <div className="flex items-center gap-3"><span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/30 hidden sm:inline">Source: local microphone</span><Chip variant="soft" size="sm" className={`px-2.5 py-0.5 font-mono text-[11px] font-semibold rounded-full border tracking-wider ${isRecording ? "bg-emerald-400/10 text-emerald-400 border-emerald-400/25" : isIdle ? "bg-[#c6ff33]/10 text-[#c6ff33] border-[#c6ff33]/25" : "bg-red-400/10 text-red-400 border-red-400/25"}`}>{isRecording ? "Recording" : isIdle ? "Ready" : "Stopped"}</Chip></div>
            </div>
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-6 py-6 sm:px-8 gap-5">
              <p className="timer-nums text-[clamp(4rem,9vw,7.5rem)] font-light leading-none text-white tracking-[-0.03em]" aria-label={`${status?.elapsed_seconds ?? 0} seconds recorded`}>{formatTime(status?.elapsed_seconds ?? 0)}</p>
              <div className="w-full"><AudioVisualizer isRecording={Boolean(isRecording)} level={status?.input_level ?? 0} /></div>
              {connectionError && <p role="alert" className="text-sm text-red-300">Backend unavailable: {connectionError}</p>}
            </div>
            <div className="border-t border-white/[0.07] px-6 py-4 sm:px-8"><div className="grid w-full gap-3 md:grid-cols-12" aria-label="Operator controls">
              <Button variant="primary" size="lg" fullWidth isDisabled={(!isRecording && !isIdle) || busy !== null} onPress={() => void runCaptureAction(isIdle ? "/api/capture/start" : "/api/capture/accept", isIdle ? "Recording started" : "Visitor saved", "Enter", "success")} className={`md:col-span-4 min-h-[64px] justify-between rounded-xl px-5 text-left ${pressedKey === "Enter" ? "key-pressed-active" : ""} bg-[#c6ff33] hover:bg-[#d4ff66] text-black font-semibold`}><div className="flex items-center gap-3">{isIdle ? <Mic className="size-5 stroke-[3]" /> : <Check className="size-5 stroke-[3]" />}<span className="font-bold text-[15px]">{isIdle ? "Start recording" : "Save & next"}</span></div><div className="flex items-center gap-1 bg-black/12 px-2 py-1 rounded-md font-mono text-[11px]"><span>Enter</span><CornerDownLeft className="size-3" /></div></Button>
              <Button variant="danger-soft" size="lg" fullWidth isDisabled={!isRecording || busy !== null} onPress={() => void runCaptureAction("/api/capture/accept-and-pause", "Feedback saved and recording paused", "", "warning")} className="md:col-span-3 min-h-[64px] justify-between rounded-xl px-4 text-left bg-red-500/20 border border-red-500/35 text-white"><div className="flex items-center gap-2.5"><Square className="size-4 text-red-400 fill-red-400" /><span className="font-semibold text-sm">Save & pause</span></div></Button>
              <Button variant="outline" size="lg" fullWidth isDisabled={!isRecording || busy !== null} onPress={() => void runCaptureAction("/api/capture/discard", "Recording discarded", "Esc", "warning")} className={`md:col-span-2 min-h-[64px] justify-between rounded-xl px-4 text-left ${pressedKey === "Escape" ? "key-pressed-active" : ""} bg-transparent border border-white/[0.14] text-white`}><div className="flex items-center gap-2.5"><RotateCcw className="size-4 text-white/50" /><span className="font-semibold text-sm">Retry</span></div><kbd>Esc</kbd></Button>
              <Button variant="danger-soft" size="lg" fullWidth isDisabled={!isRecording || busy !== null} onPress={() => void runCaptureAction("/api/capture/stop", "Capture stopped", "Q", "stop")} className={`md:col-span-3 min-h-[64px] justify-between rounded-xl px-4 text-left ${pressedKey === "Q" ? "key-pressed-active" : ""} bg-red-500/20 border border-red-500/35 text-white`}><div className="flex items-center gap-2.5"><Square className="size-4 text-red-400 fill-red-400" /><span className="font-semibold text-sm">Stop capture</span></div><kbd>Q</kbd></Button>
            </div></div>
          </div>
        </motion.section>
        <footer className="flex h-8 shrink-0 items-center justify-between text-[10px] text-white/30"><span>Python controls the microphone and transcript pipeline.</span><span>Press <kbd className="text-[9px]">?</kbd> for shortcuts</span></footer>
      </div>
    </main>
  );
}
