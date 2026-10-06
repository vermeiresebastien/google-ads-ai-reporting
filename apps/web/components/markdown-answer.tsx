"use client";

import { Fragment, memo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type SummaryHighlight = {
  id: string;
  quote: string;
  color: string;
  note: string;
};

export const HIGHLIGHT_CLASS: Record<string, string> = {
  yellow: "bg-amber-200",
  green: "bg-emerald-200",
  blue: "bg-sky-200",
  pink: "bg-rose-200",
};

function quoteParts(quote: string) {
  return quote
    .split(/\n+/)
    .map((part) => part.trim())
    .filter((part) => part.length >= 2);
}

function keepsWordBoundary(text: string, start: number, end: number) {
  const word = /[\p{L}\p{N}]/u;
  const before = start > 0 ? text[start - 1] : "";
  const after = end < text.length ? text[end] : "";
  if (word.test(text[start] ?? "") && word.test(before)) return false;
  if (word.test(text[end - 1] ?? "") && word.test(after)) return false;
  return true;
}

function findRanges(text: string, quote: string) {
  const ranges: { start: number; end: number }[] = [];
  const push = (start: number, end: number) => {
    if (keepsWordBoundary(text, start, end)) ranges.push({ start, end });
  };
  let from = 0;
  while (from < text.length) {
    const index = text.indexOf(quote, from);
    if (index < 0) break;
    push(index, index + quote.length);
    from = index + quote.length;
  }
  if (ranges.length) return ranges;
  const parts = quote.split(/\s+/).filter(Boolean).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!parts.length) return ranges;
  for (const match of text.matchAll(new RegExp(parts.join("\\s+"), "g"))) {
    if (match.index == null) continue;
    push(match.index, match.index + match[0].length);
  }
  return ranges;
}

function stopControlEvent(event: { preventDefault: () => void; stopPropagation: () => void }) {
  event.preventDefault();
  event.stopPropagation();
}

function CommentBalloon({ highlight, onRemove }: { highlight: SummaryHighlight; onRemove?: (highlightId: string) => void }) {
  return (
    <span className="group relative inline-flex align-super">
      <button
        type="button"
        aria-label="Show comment"
        className="ml-0.5 inline-flex h-3.5 w-3.5 select-none items-center justify-center rounded-full text-neutral-500 hover:text-neutral-900"
        onMouseDown={stopControlEvent}
        onMouseUp={stopControlEvent}
      >
        <svg viewBox="0 0 16 16" className="h-3 w-3" aria-hidden="true">
          <path
            fill="currentColor"
            d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v6A1.5 1.5 0 0 1 12.5 11H6.2L3 13.4V3.5Z"
          />
        </svg>
      </button>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-30 hidden -translate-x-1/2 pb-1 group-hover:pointer-events-auto group-hover:block group-focus-within:pointer-events-auto group-focus-within:block">
        <span className="block w-56 rounded-md border border-line bg-white p-2 text-left text-xs font-normal normal-case leading-5 text-neutral-800 shadow-sm">
          {highlight.note}
          {onRemove ? (
            <button
              type="button"
              className="mt-2 block text-red-700"
              onMouseDown={stopControlEvent}
              onMouseUp={stopControlEvent}
              onClick={(event) => {
                stopControlEvent(event);
                onRemove(highlight.id);
              }}
            >
              Remove
            </button>
          ) : null}
        </span>
      </span>
    </span>
  );
}

function markQuotes(text: string, highlights: SummaryHighlight[], onRemove?: (highlightId: string) => void, forPrint = false): ReactNode {
  const spans: { start: number; end: number; highlight: SummaryHighlight }[] = [];
  for (const highlight of highlights) {
    for (const quote of quoteParts(highlight.quote)) {
      for (const range of findRanges(text, quote)) spans.push({ ...range, highlight });
    }
  }
  spans.sort((left, right) => left.start - right.start || right.end - left.end);
  const chosen: typeof spans = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start < cursor) continue;
    chosen.push(span);
    cursor = span.end;
  }
  if (!chosen.length) return text;
  const nodes: ReactNode[] = [];
  let position = 0;
  const balloonShown = new Set<string>();
  chosen.forEach((span, index) => {
    if (span.start > position) nodes.push(text.slice(position, span.start));
    const showBalloon = Boolean(span.highlight.note) && !balloonShown.has(span.highlight.id);
    if (showBalloon) balloonShown.add(span.highlight.id);
    nodes.push(
      <mark key={`${span.highlight.id}-${index}`} className={`rounded px-0.5 text-inherit ${HIGHLIGHT_CLASS[span.highlight.color] ?? "bg-amber-200"}`}>
        {text.slice(span.start, span.end)}
        {showBalloon && forPrint ? <span className="ml-1 text-xs italic text-neutral-700">({span.highlight.note})</span> : null}
        {showBalloon && !forPrint ? <CommentBalloon highlight={span.highlight} onRemove={onRemove} /> : null}
        {!forPrint && onRemove && !span.highlight.note ? (
          <button
            type="button"
            aria-label="Remove highlight"
            className="ml-1 select-none text-[10px] leading-none text-neutral-500 hover:text-red-700"
            onMouseDown={stopControlEvent}
            onMouseUp={stopControlEvent}
            onClick={(event) => {
              stopControlEvent(event);
              onRemove(span.highlight.id);
            }}
          >
            ×
          </button>
        ) : null}
      </mark>,
    );
    position = span.end;
  });
  if (position < text.length) nodes.push(text.slice(position));
  return nodes;
}

function decorate(node: ReactNode, highlights: SummaryHighlight[], onRemove?: (highlightId: string) => void, forPrint = false): ReactNode {
  if (!highlights.length) return node;
  if (typeof node === "string" || typeof node === "number") return markQuotes(String(node), highlights, onRemove, forPrint);
  if (Array.isArray(node)) {
    return node.map((child, index) => <Fragment key={index}>{decorate(child, highlights, onRemove, forPrint)}</Fragment>);
  }
  return node;
}

function Heading({ level, children }: { level: 3 | 4; children?: ReactNode }) {
  const className = level === 3 ? "text-base font-semibold text-neutral-900" : "text-sm font-semibold text-neutral-900";
  return level === 3 ? <h3 className={className}>{children}</h3> : <h4 className={className}>{children}</h4>;
}

export const MarkdownAnswer = memo(function MarkdownAnswer({
  text,
  highlights = [],
  onRemove,
  forPrint = false,
}: {
  text: string;
  highlights?: SummaryHighlight[];
  onRemove?: (highlightId: string) => void;
  forPrint?: boolean;
}) {
  const marked = (children: ReactNode) => decorate(children, highlights, onRemove, forPrint);
  return (
    <div className="space-y-3 text-sm leading-6 text-neutral-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <Heading level={3}>{marked(children)}</Heading>,
          h2: ({ children }) => <Heading level={3}>{marked(children)}</Heading>,
          h3: ({ children }) => <Heading level={4}>{marked(children)}</Heading>,
          p: ({ children }) => <p>{marked(children)}</p>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{marked(children)}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{marked(children)}</ol>,
          li: ({ children }) => <li>{marked(children)}</li>,
          strong: ({ children }) => <strong className="font-semibold text-neutral-900">{marked(children)}</strong>,
          a: ({ href, children }) => (
            <a href={href} className="text-pine underline" target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          blockquote: ({ children }) => <blockquote className="border-l-2 border-line pl-3 text-neutral-600">{marked(children)}</blockquote>,
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border-b border-line px-2 py-1 font-medium">{marked(children)}</th>,
          td: ({ children }) => <td className="border-b border-line px-2 py-1 align-top">{marked(children)}</td>,
          hr: () => <hr className="border-line" />,
          pre: ({ children }) => <pre className="overflow-x-auto rounded-md bg-paper p-3 text-xs">{children}</pre>,
          code: ({ className, children }) =>
            className ? (
              <code className={className}>{children}</code>
            ) : (
              <code className="rounded bg-paper px-1 py-0.5 text-[0.85em]">{children}</code>
            ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
