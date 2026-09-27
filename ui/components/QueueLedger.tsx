"use client";

export type QueueItem = {
  visitor_id: string;
  status: string;
  error?: string | null;
};

export type QueueSnapshot = {
  counts: Record<string, number>;
  items: QueueItem[];
};

const STATUS_COPY: Record<string, string> = {
  pending: "Waiting",
  normalizing: "Checking audio",
  transcribing: "Writing speech",
  completed: "Transcript ready",
  failed: "Not used",
};

function statusTone(status: string) {
  if (status === "completed") return "text-[var(--celadon)]";
  if (status === "failed") return "text-[var(--rust)]";
  if (status === "transcribing" || status === "normalizing") return "text-[var(--copper)]";
  return "text-[var(--muted)]";
}

export function QueueLedger({ queue }: { queue: QueueSnapshot | undefined }) {
  const items = queue?.items ?? [];
  const counts = queue?.counts ?? {};
  const open =
    (counts.pending ?? 0) + (counts.normalizing ?? 0) + (counts.transcribing ?? 0);
  const done = counts.completed ?? 0;
  const failed = counts.failed ?? 0;

  return (
    <aside
      className="flex h-full min-h-0 flex-col border-[var(--hairline)] bg-[var(--vitrine)] max-lg:border-t lg:border-l"
      aria-label="Accepted recordings"
    >
      <div className="flex items-baseline justify-between gap-3 border-b border-[var(--hairline)] px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
            Accession ledger
          </p>
          <p className="font-display mt-1 text-lg text-[var(--bone)]">Kept takes</p>
        </div>
        <p className="font-mono text-[11px] text-[var(--muted)] tabular-nums">
          {open} in flight · {done} ready
          {failed ? ` · ${failed} unused` : ""}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {items.length === 0 ? (
          <p className="px-3 py-8 text-sm leading-relaxed text-[var(--muted)] text-pretty">
            Saved visitors appear here while audio is checked and turned into text. Nothing is billed until a take is kept.
          </p>
        ) : (
          <ol className="flex flex-col gap-0.5">
            {[...items].reverse().map((item) => (
              <li
                key={item.visitor_id}
                className="flex items-start justify-between gap-3 rounded-lg px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="font-mono text-[13px] text-[var(--bone)] tabular-nums">{item.visitor_id}</p>
                  {item.status === "failed" && item.error ? (
                    <p className="mt-0.5 truncate text-xs text-[var(--rust)]" title={item.error}>
                      {item.error}
                    </p>
                  ) : null}
                </div>
                <span className={`shrink-0 text-xs ${statusTone(item.status)}`}>
                  {STATUS_COPY[item.status] ?? item.status}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
