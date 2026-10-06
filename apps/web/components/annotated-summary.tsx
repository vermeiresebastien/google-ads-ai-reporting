"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { MarkdownAnswer, type SummaryHighlight } from "@/components/markdown-answer";

const COLORS = [
  { id: "yellow", label: "Yellow", swatch: "bg-amber-200" },
  { id: "green", label: "Green", swatch: "bg-emerald-200" },
  { id: "blue", label: "Blue", swatch: "bg-sky-200" },
  { id: "pink", label: "Pink", swatch: "bg-rose-200" },
] as const;

export function AnnotatedSummary({
  text,
  highlights,
  onAdd,
  onRemove,
}: {
  text: string;
  highlights: SummaryHighlight[];
  onAdd: (quote: string, color: string, note: string) => Promise<void>;
  onRemove: (highlightId: string) => Promise<void>;
}) {
  const [selection, setSelection] = useState<{ quote: string } | null>(null);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);
  const [note, setNote] = useState("");
  const noteRef = useRef("");
  const quoteRef = useRef("");
  const movedRef = useRef(false);
  const rangeRef = useRef<Range | null>(null);
  const dragRef = useRef<{ dx: number; dy: number; pointerId: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function rememberNote(value: string) {
    noteRef.current = value;
    setNote(value);
  }

  function placeBox(top: number, left: number) {
    setBox({
      top: Math.min(Math.max(top, 8), window.innerHeight - 140),
      left: Math.min(Math.max(left, 8), window.innerWidth - 272),
    });
  }

  function startDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!box) return;
    event.preventDefault();
    dragRef.current = { dx: event.clientX - box.left, dy: event.clientY - box.top, pointerId: event.pointerId };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    movedRef.current = true;
    placeBox(event.clientY - dragRef.current.dy, event.clientX - dragRef.current.dx);
  }

  function endDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  }

  function captureSelection(event: React.MouseEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement;
    if (target.closest("button")) return;
    const selected = window.getSelection();
    const quote = (selected?.toString() ?? "").replace(/×/g, " ").replace(/\s+/g, " ").trim();
    const anchor = selected?.anchorNode ?? null;
    if (!quote || quote.length < 2 || !anchor || !event.currentTarget.contains(anchor)) {
      return;
    }
    const range = selected && selected.rangeCount ? selected.getRangeAt(0) : null;
    const rect = range ? range.getBoundingClientRect() : null;
    if (!range || !rect || rect.width === 0) return;
    setError("");
    if (quoteRef.current !== quote) {
      quoteRef.current = quote;
      rememberNote("");
    }
    if (!movedRef.current) placeBox(rect.bottom + 8, rect.left);
    rangeRef.current = range.cloneRange();
    setSelection({ quote });
  }

  useLayoutEffect(() => {
    const range = rangeRef.current;
    if (!selection || !range) return;
    const selected = window.getSelection();
    if (!selected || selected.toString().replace(/\s+/g, " ").trim() === selection.quote) return;
    selected.removeAllRanges();
    try {
      selected.addRange(range);
    } catch {
      rangeRef.current = null;
    }
  }, [selection, box]);

  async function paint(color: string) {
    if (!selection) return;
    const comment = noteRef.current;
    setBusy(true);
    setError("");
    try {
      await onAdd(selection.quote, color, comment);
      rememberNote("");
      quoteRef.current = "";
      movedRef.current = false;
      rangeRef.current = null;
      setSelection(null);
      setBox(null);
      window.getSelection()?.removeAllRanges();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Highlight failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="mb-2 text-xs text-neutral-500">Select text, write a comment if you want one, then choose a color.</p>
      <div onMouseUp={captureSelection}>
        <MarkdownAnswer text={text} highlights={highlights} onRemove={onRemove} />
      </div>
      {selection && box ? (
        <div
          className="fixed z-20 w-64 rounded-md border border-line bg-white p-2 shadow-sm"
          style={{ top: box.top, left: box.left }}
          onMouseDown={(event) => {
            if ((event.target as HTMLElement).closest("[data-drag-handle]")) return;
            if ((event.target as HTMLElement).tagName !== "INPUT") event.preventDefault();
          }}
        >
          <div
            data-drag-handle
            role="button"
            aria-label="Drag to move"
            className="mb-2 cursor-grab select-none text-xs text-neutral-500 active:cursor-grabbing"
            onPointerDown={startDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
          >
            Drag to move
          </div>
          <input
            className="mb-2 w-full rounded-md border border-line px-2 py-1 text-xs"
            placeholder="Note (optional)"
            value={note}
            onChange={(event) => rememberNote(event.target.value)}
            aria-label="Highlight note"
          />
          <div className="flex gap-2">
            {COLORS.map((color) => (
              <button
                key={color.id}
                type="button"
                aria-label={color.label}
                disabled={busy}
                className={`h-6 w-6 rounded-full border border-line ${color.swatch}`}
                onClick={() => paint(color.id)}
              />
            ))}
          </div>
          {error ? <p className="mt-2 text-xs text-red-700">{error}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
