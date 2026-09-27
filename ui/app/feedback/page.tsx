"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Brain, CircleAlert, LoaderCircle } from "lucide-react";

type Project = {
  project_id: string;
  name: string;
  zone?: { number?: string; name?: string } | null;
};

type FeedbackItem = {
  visitor_id: string;
  text: string;
  segments: Array<{ start?: number; end?: number; text?: string }>;
  classification: { status: string; project_ids: string[]; error?: string | null };
  projects: Project[];
};

export default function FeedbackPage() {
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/feedback", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error?.message ?? "Unable to read feedback.");
        return payload.data.items as FeedbackItem[];
      })
      .then((nextItems) => {
        if (!active) return;
        setItems(nextItems);
        setSelectedId(nextItems[0]?.visitor_id ?? null);
      })
      .catch((nextError) => {
        if (active) setError(nextError instanceof Error ? nextError.message : "Unable to read feedback.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const selected = items.find((item) => item.visitor_id === selectedId) ?? null;

  return (
    <main id="booth-main" className="booth-shell flex min-h-svh flex-col text-[var(--bone)]">
      <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-[var(--hairline)] px-4 sm:px-6">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">AI Museum · KIT</p>
          <h1 className="font-display truncate text-lg leading-tight sm:text-xl">Feedback stack</h1>
        </div>
        <a href="/" className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-[var(--muted)] hover:bg-white/5 hover:text-[var(--bone)]">
          <ArrowLeft className="size-3.5" aria-hidden="true" />
          Booth
        </a>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(280px,0.48fr)_minmax(0,1fr)]">
        <aside className="min-h-0 border-b border-[var(--hairline)] bg-[var(--vitrine)] lg:border-b-0 lg:border-r" aria-label="Feedback transcripts">
          <div className="flex items-baseline justify-between gap-3 border-b border-[var(--hairline)] px-5 py-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Accession ledger</p>
              <p className="font-display mt-1 text-lg text-[var(--bone)]">Visitor voices</p>
            </div>
            <p className="font-mono text-[11px] text-[var(--muted)] tabular-nums">{items.length} saved</p>
          </div>

          <div className="max-h-[38vh] overflow-y-auto p-2 lg:max-h-none lg:h-[calc(100vh-65px)]">
            {loading ? (
              <p className="flex items-center gap-2 px-3 py-8 text-sm text-[var(--muted)]"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />Loading feedback…</p>
            ) : error ? (
              <p role="alert" className="px-3 py-8 text-sm leading-relaxed text-[var(--rust)]">{error}</p>
            ) : items.length === 0 ? (
              <p className="px-3 py-8 text-sm leading-relaxed text-[var(--muted)]">Completed transcripts appear here after the booth finishes transcribing them.</p>
            ) : (
              <ol className="flex flex-col gap-1">
                {items.map((item) => {
                  const active = item.visitor_id === selectedId;
                  return (
                    <li key={item.visitor_id}>
                      <button
                        type="button"
                        aria-expanded={active}
                        aria-controls={`feedback-${item.visitor_id}`}
                        onClick={() => setSelectedId(item.visitor_id)}
                        className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${active ? "border-[rgba(232,224,208,0.25)] bg-[var(--ledge)]" : "border-transparent hover:bg-white/5"}`}
                      >
                        <span className="flex items-center justify-between gap-3">
                          <span className="font-mono text-[13px] text-[var(--bone)] tabular-nums">{item.visitor_id}</span>
                          <span className={`text-[11px] ${item.classification.status === "completed" ? "text-[var(--celadon)]" : item.classification.status === "failed" ? "text-[var(--rust)]" : "text-[var(--copper)]"}`}>
                            {item.classification.status === "completed" ? `${item.projects.length} project${item.projects.length === 1 ? "" : "s"}` : item.classification.status === "failed" ? "Needs review" : "Classifying…"}
                          </span>
                        </span>
                        <span className="mt-1 block truncate text-xs text-[var(--muted)]">{item.text}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </aside>

        <section id={selected ? `feedback-${selected.visitor_id}` : "feedback-detail"} className="min-h-0 overflow-y-auto px-4 py-6 sm:px-8" aria-live="polite" aria-label="Selected feedback">
          {selected ? (
            <article className="mx-auto max-w-3xl">
              <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--hairline)] pb-5">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Selected visitor</p>
                  <h2 className="font-display mt-1 text-3xl text-[var(--bone)]">{selected.visitor_id}</h2>
                </div>
                <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                  <Brain className="size-4" aria-hidden="true" />
                  {selected.classification.status === "completed" ? "Project links ready" : selected.classification.status === "failed" ? "Classification failed" : "Classifying…"}
                </div>
              </div>

              <section className="py-7" aria-labelledby="transcript-heading">
                <p id="transcript-heading" className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Transcript</p>
                <p className="mt-3 whitespace-pre-wrap text-lg leading-relaxed text-[var(--paper)]">{selected.text}</p>
              </section>

              <section id="projects" className="border-t border-[var(--hairline)] py-6" aria-labelledby="projects-heading">
                <div className="flex items-baseline justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">Agent read</p>
                    <h3 id="projects-heading" className="font-display mt-1 text-2xl text-[var(--bone)]">Mentioned projects</h3>
                  </div>
                  <span className="font-mono text-xs text-[var(--muted)]">{selected.projects.length}</span>
                </div>

                {selected.classification.status === "pending" ? (
                  <p className="mt-5 flex items-center gap-2 text-sm text-[var(--copper)]"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />Agent is reading this feedback.</p>
                ) : selected.classification.status === "failed" ? (
                  <p role="alert" className="mt-5 flex items-start gap-2 text-sm text-[var(--rust)]"><CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{selected.classification.error ?? "The agent could not classify this feedback."}</p>
                ) : selected.projects.length === 0 ? (
                  <p className="mt-5 text-sm text-[var(--muted)]">No project was explicitly connected to this feedback.</p>
                ) : (
                  <ul className="mt-5 grid gap-3 sm:grid-cols-2">
                    {selected.projects.map((project) => (
                      <li id={`project-${project.project_id}`} key={project.project_id} className="rounded-lg border border-[var(--hairline)] bg-[var(--vitrine)] p-4">
                        <a href={`#project-${project.project_id}`} className="text-sm font-semibold text-[var(--paper)] hover:underline">{project.name}</a>
                        {project.zone?.name ? <p className="mt-1 text-xs text-[var(--muted)]">Zone {project.zone.number ?? "—"} · {project.zone.name}</p> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </article>
          ) : (
            <div className="flex min-h-[50vh] items-center justify-center text-center text-sm text-[var(--muted)]">Select a transcript to inspect its project connections.</div>
          )}
        </section>
      </div>
    </main>
  );
}
