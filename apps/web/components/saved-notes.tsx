"use client";

import { useEffect, useRef, useState } from "react";
import { AnnotatedSummary } from "@/components/annotated-summary";
import { HIGHLIGHT_CLASS, MarkdownAnswer, type SummaryHighlight } from "@/components/markdown-answer";
import { RangeCalendar } from "@/components/range-calendar";
import { API_URL, api, token } from "@/lib/api";

export type SavedNote = {
  id: string;
  report_date: string;
  kind: string;
  period_start: string | null;
  period_end: string | null;
  question: string;
  title: string;
  body: string;
  updated_at: string | null;
  highlights: SummaryHighlight[];
};

export type NotePrint = {
  view: "full" | "note" | "period";
  selected: SavedNote | null;
  visible: SavedNote[];
  spanLabel: string;
};

function covers(item: SavedNote, start: string, end: string) {
  const itemStart = item.period_start ?? item.report_date;
  const itemEnd = item.period_end ?? item.report_date;
  return itemStart <= end && itemEnd >= start;
}

export function noteLabel(item: SavedNote) {
  const custom = item.title?.trim();
  if (custom) return custom;
  const text = item.question.trim() || "Long-term overview";
  return text.length > 80 ? `${text.slice(0, 77)}…` : text;
}

function fileSlug(value: string) {
  const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return slug.slice(0, 80) || "summary";
}

function pdfFileName(item: SavedNote, view: "full" | "note" | "period", rangeStart: string, rangeEnd: string) {
  if (view === "period") {
    const start = rangeStart || item.period_start || item.report_date;
    const end = rangeEnd || item.period_end || item.report_date;
    return start === end ? `${start}-highlights` : `${start}-to-${end}-highlights`;
  }
  const date = item.period_start || item.report_date;
  return `${date}-${fileSlug(noteLabel(item))}-${view === "note" ? "highlights" : "full"}`;
}

function downloadPdf(name: string) {
  const previous = document.title;
  const restore = () => {
    document.title = previous;
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);
  document.title = name;
  window.print();
}

function HighlightBits({
  groups,
  empty,
  showTitles = false,
  onOpen,
}: {
  groups: { id: string; title: string; highlights: SummaryHighlight[] }[];
  empty: string;
  showTitles?: boolean;
  onOpen?: (id: string) => void;
}) {
  const filled = groups.filter((group) => group.highlights.length > 0);
  if (!filled.length) return <p className="text-sm text-neutral-600">{empty}</p>;
  return (
    <div className="space-y-4">
      {filled.map((group) => (
        <section key={group.id}>
          {showTitles ? (
            onOpen ? (
              <button type="button" className="mb-2 text-sm font-medium text-neutral-900" onClick={() => onOpen(group.id)}>
                {group.title}
              </button>
            ) : (
              <h2 className="mb-2 text-sm font-semibold text-neutral-900">{group.title}</h2>
            )
          ) : null}
          <ul className="space-y-2">
            {group.highlights.map((highlight) => (
              <li key={highlight.id}>
                <mark className={`rounded px-0.5 text-sm leading-6 text-inherit ${HIGHLIGHT_CLASS[highlight.color] ?? "bg-amber-200"}`}>
                  {highlight.quote}
                </mark>
                {highlight.note ? <p className="mt-1 text-xs italic text-neutral-700">{highlight.note}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function SavedNotePrint({ state }: { state: NotePrint | null }) {
  if (!state) return null;
  const { view, selected, visible, spanLabel } = state;
  const period = selected
    ? selected.period_start && selected.period_end
      ? `${selected.period_start} – ${selected.period_end}`
      : selected.report_date
    : "";
  return (
    <article className="hidden bg-white p-8 text-neutral-900 print:block">
      {view === "period" ? (
        <>
          <h1 className="mb-6 text-2xl font-semibold">Highlights · {spanLabel}</h1>
          <HighlightBits
            groups={visible.map((item) => ({ id: item.id, title: noteLabel(item), highlights: item.highlights ?? [] }))}
            empty={`No highlighted text in ${spanLabel}.`}
            showTitles
          />
        </>
      ) : selected ? (
        <>
          <h1 className="mb-1 text-2xl font-semibold">{noteLabel(selected)}</h1>
          <p className="mb-6 text-sm text-neutral-600">{period} · Saved {selected.report_date}</p>
          {view === "note" ? (
            <HighlightBits
              groups={[{ id: selected.id, title: noteLabel(selected), highlights: selected.highlights ?? [] }]}
              empty="This note has no highlighted text."
            />
          ) : (
            <MarkdownAnswer text={selected.body} highlights={selected.highlights ?? []} forPrint />
          )}
        </>
      ) : null}
    </article>
  );
}

export function SavedNotes({
  notes,
  accountId,
  zipPath,
  focusId = "",
  onReload,
  onPrint,
  onExpandedChange,
}: {
  notes: SavedNote[];
  accountId: string;
  zipPath: string;
  focusId?: string;
  onReload: () => void;
  onPrint: (state: NotePrint) => void;
  onExpandedChange?: (open: boolean) => void;
}) {
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [rename, setRename] = useState<{ id: string; where: "list" | "note" } | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState("");
  const [highlightView, setHighlightView] = useState<"full" | "note" | "period">("full");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [exportError, setExportError] = useState("");
  const [archiveError, setArchiveError] = useState("");
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const today = new Date();
    return { year: today.getFullYear(), month: today.getMonth() };
  });
  const skipRename = useRef(false);
  const seenFocus = useRef("");
  const onPrintRef = useRef(onPrint);
  onPrintRef.current = onPrint;
  const onExpandedRef = useRef(onExpandedChange);
  onExpandedRef.current = onExpandedChange;

  const savedDates = new Set(notes.map((item) => item.report_date));
  const visible = rangeStart && rangeEnd ? notes.filter((item) => covers(item, rangeStart, rangeEnd)) : [];
  const selected = visible.find((item) => item.id === selectedId) ?? visible[0];
  const spanLabel = rangeStart && rangeStart === rangeEnd ? rangeStart : `${rangeStart} – ${rangeEnd}`;

  function focusMonth(iso: string) {
    const [year, month] = iso.split("-").map(Number);
    if (year && month) setVisibleMonth({ year, month: month - 1 });
  }

  function setSpan(start: string, end: string) {
    if (!start || !end) return;
    const [from, to] = start <= end ? [start, end] : [end, start];
    setRangeStart(from);
    setRangeEnd(to);
    setSelectedId("");
  }

  function pickDay(iso: string) {
    if (!rangeStart || rangeStart !== rangeEnd) setSpan(iso, iso);
    else setSpan(rangeStart, iso);
  }

  useEffect(() => {
    onExpandedRef.current?.(archiveOpen);
  }, [archiveOpen]);

  useEffect(() => {
    if (rangeStart || notes.length === 0) return;
    const latest = notes[0].report_date;
    setRangeStart(latest);
    setRangeEnd(latest);
    focusMonth(latest);
  }, [notes, rangeStart]);

  useEffect(() => {
    if (!focusId || focusId === seenFocus.current) return;
    const note = notes.find((item) => item.id === focusId);
    if (!note) return;
    seenFocus.current = focusId;
    setSelectedId(focusId);
    setArchiveOpen(true);
    const start = note.period_start ?? note.report_date;
    const end = note.period_end ?? note.report_date;
    setRangeStart(start);
    setRangeEnd(end);
    focusMonth(end);
  }, [focusId, notes]);

  useEffect(() => {
    onPrintRef.current({ view: highlightView, selected: selected ?? null, visible, spanLabel });
  }, [highlightView, rangeStart, rangeEnd, selectedId, notes, spanLabel]);

  function beginRename(item: SavedNote, where: "list" | "note") {
    skipRename.current = false;
    setSelectedId(item.id);
    setRename({ id: item.id, where });
    setDraftTitle(noteLabel(item));
  }

  async function commitRename(item: SavedNote) {
    if (skipRename.current) {
      skipRename.current = false;
      return;
    }
    const next = draftTitle.trim();
    setRename(null);
    if (!accountId || next === noteLabel(item)) return;
    setArchiveError("");
    try {
      await api(`/api/reports/saved/${item.id}?account_id=${accountId}`, {
        method: "PATCH",
        body: JSON.stringify({ title: next }),
      });
      onReload();
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Could not rename the trend");
    }
  }

  async function removeSaved(reportId: string) {
    if (!accountId) return;
    setPendingDeleteId("");
    setArchiveError("");
    try {
      await api(`/api/reports/saved/${reportId}?account_id=${accountId}`, { method: "DELETE" });
      if (selectedId === reportId) setSelectedId("");
      if (rename?.id === reportId) setRename(null);
      onReload();
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Delete failed");
    }
  }

  async function addHighlight(reportId: string, quote: string, color: string, note: string) {
    if (!accountId) return;
    setArchiveError("");
    try {
      await api(`/api/reports/saved/${reportId}/highlights?account_id=${accountId}`, {
        method: "POST",
        body: JSON.stringify({ quote, color, note }),
      });
      onReload();
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Could not save the highlight");
    }
  }

  async function removeHighlight(reportId: string, highlightId: string) {
    if (!accountId) return;
    setArchiveError("");
    try {
      await api(`/api/reports/saved/${reportId}/highlights/${highlightId}?account_id=${accountId}`, { method: "DELETE" });
      onReload();
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Could not remove the highlight");
    }
  }

  async function downloadZip() {
    if (!accountId || !rangeStart || !rangeEnd) return;
    setExportError("");
    try {
      const response = await fetch(`${API_URL}${zipPath}?account_id=${accountId}&start=${rangeStart}&end=${rangeEnd}`, {
        headers: token() ? { Authorization: `Bearer ${token()}` } : {},
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Download failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const header = response.headers.get("Content-Disposition") ?? "";
      const match = header.match(/filename="([^"]+)"/);
      link.href = url;
      link.download = match?.[1] ?? (rangeStart === rangeEnd ? `${rangeStart}-trends.zip` : `${rangeStart}-to-${rangeEnd}-trends.zip`);
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setExportError(reason instanceof Error ? reason.message : "Download failed");
    }
  }

  return (
    <>
      <section className="mt-6 rounded-xl border border-line bg-white p-4">
        <button
          type="button"
          className="flex w-full items-center justify-between text-left"
          aria-expanded={archiveOpen}
          onClick={() => setArchiveOpen((open) => !open)}
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Saved trends{notes.length ? ` (${notes.length})` : ""}
          </h2>
          <span className="text-sm text-neutral-500">{archiveOpen ? "Hide" : "Show"}</span>
        </button>
        {archiveOpen ? (
          <div className="mt-4">
            {notes.length === 0 ? (
              <p className="text-sm text-neutral-600">A trend is kept when you ask the council.</p>
            ) : (
              <div className="grid gap-4 lg:grid-cols-[11rem_1fr]">
                <div>
                  <RangeCalendar
                    year={visibleMonth.year}
                    month={visibleMonth.month}
                    onMonth={setVisibleMonth}
                    start={rangeStart}
                    end={rangeEnd}
                    marked={savedDates}
                    onPick={pickDay}
                    onSpan={setSpan}
                    hint="Start day, then end day. Dots mark a saved trend."
                  />
                  <button type="button" className="mt-2 w-full rounded-md bg-pine px-2 py-1 text-xs text-white disabled:opacity-40" disabled={!rangeStart || !rangeEnd} onClick={downloadZip}>
                    Download zip
                  </button>
                  <p className="mt-2 text-xs text-neutral-500">Each file is one saved trend in this period.</p>
                  {exportError ? <p className="mt-2 text-xs text-red-700">{exportError}</p> : null}
                  {archiveError ? <p className="mt-2 text-xs text-red-700">{archiveError}</p> : null}
                </div>
                <div>
                  {visible.length === 0 ? (
                    <p className="text-sm text-neutral-600">{rangeStart ? `No saved trend covers ${spanLabel}.` : "Pick a start and end date to read trends for that period."}</p>
                  ) : (
                    <>
                      <div className="mb-3 flex flex-wrap gap-2">
                        {visible.map((item) => (
                          <div
                            key={item.id}
                            className={`rounded-md border px-2 py-1 text-sm ${selected?.id === item.id ? "border-pine bg-paper" : "border-line"}`}
                            onClick={() => setSelectedId(item.id)}
                          >
                            {rename?.id === item.id && rename.where === "list" ? (
                              <input
                                aria-label="Trend title"
                                className="w-full rounded border border-line bg-white px-1 py-0.5 text-sm"
                                value={draftTitle}
                                autoFocus
                                onClick={(event) => event.stopPropagation()}
                                onChange={(event) => setDraftTitle(event.target.value)}
                                onBlur={() => commitRename(item)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    event.currentTarget.blur();
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    skipRename.current = true;
                                    setRename(null);
                                  }
                                }}
                              />
                            ) : (
                              <span
                                className={`block ${selected?.id === item.id ? "font-medium" : ""}`}
                                title="Double-click to rename"
                                onDoubleClick={(event) => {
                                  event.stopPropagation();
                                  beginRename(item, "list");
                                }}
                              >
                                {noteLabel(item)}
                              </span>
                            )}
                            <span className="block text-xs text-neutral-500">{item.period_start && item.period_end ? `${item.period_start} – ${item.period_end}` : item.report_date}</span>
                            <span className="block text-xs text-neutral-500">Saved {item.report_date}</span>
                          </div>
                        ))}
                      </div>
                      {selected ? (
                        <div>
                          <div className="mb-2 flex items-start justify-between gap-3">
                            {rename?.id === selected.id && rename.where === "note" ? (
                              <input
                                aria-label="Trend title"
                                className="min-w-0 flex-1 rounded border border-line bg-white px-2 py-1 text-base font-semibold"
                                value={draftTitle}
                                autoFocus
                                onChange={(event) => setDraftTitle(event.target.value)}
                                onBlur={() => commitRename(selected)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    event.currentTarget.blur();
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    skipRename.current = true;
                                    setRename(null);
                                  }
                                }}
                              />
                            ) : (
                              <h3
                                className="text-base font-semibold text-neutral-900"
                                title="Double-click to rename"
                                onDoubleClick={() => beginRename(selected, "note")}
                              >
                                {noteLabel(selected)}
                              </h3>
                            )}
                            <div className="flex shrink-0 gap-3">
                              <button type="button" className="text-xs text-pine" onClick={() => downloadPdf(pdfFileName(selected, highlightView, rangeStart, rangeEnd))}>
                                Download PDF
                              </button>
                              <button type="button" className="text-xs text-red-700" onClick={() => setPendingDeleteId(selected.id)}>
                                Delete
                              </button>
                            </div>
                          </div>
                          <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="What to show">
                            {(
                              [
                                ["full", "Full note"],
                                ["note", "Highlights in this note"],
                                ["period", "Highlights in this period"],
                              ] as const
                            ).map(([value, label]) => (
                              <button
                                key={value}
                                type="button"
                                aria-pressed={highlightView === value}
                                className={`rounded-md border px-2 py-1 text-xs ${highlightView === value ? "border-pine bg-paper font-medium" : "border-line"}`}
                                onClick={() => setHighlightView(value)}
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                          {highlightView === "full" ? (
                            <AnnotatedSummary
                              text={selected.body}
                              highlights={selected.highlights ?? []}
                              onAdd={(quote, color, note) => addHighlight(selected.id, quote, color, note)}
                              onRemove={(highlightId) => removeHighlight(selected.id, highlightId)}
                            />
                          ) : highlightView === "note" ? (
                            <HighlightBits
                              groups={[{ id: selected.id, title: noteLabel(selected), highlights: selected.highlights ?? [] }]}
                              empty="This note has no highlighted text."
                            />
                          ) : (
                            <HighlightBits
                              groups={visible.map((item) => ({ id: item.id, title: noteLabel(item), highlights: item.highlights ?? [] }))}
                              empty={`No highlighted text in ${spanLabel}.`}
                              showTitles
                              onOpen={setSelectedId}
                            />
                          )}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </section>
      {pendingDeleteId ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="presentation" onClick={() => setPendingDeleteId("")}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-trend-title"
            className="w-full max-w-sm rounded-lg border border-line bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="delete-trend-title" className="text-base font-semibold text-neutral-900">Delete this saved trend?</h3>
            <p className="mt-2 text-sm text-neutral-600">The trend and its highlights will be removed.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => setPendingDeleteId("")}>
                Cancel
              </button>
              <button type="button" className="rounded-md bg-red-700 px-3 py-1.5 text-sm text-white" onClick={() => removeSaved(pendingDeleteId)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
