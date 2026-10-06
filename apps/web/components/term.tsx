"use client";

import { useState } from "react";
import { createPortal } from "react-dom";

const HELP: Record<string, string> = {
  "total spend": "The amount Google Ads charged in this period.",
  spend: "The amount Google Ads charged in this period.",
  "earlier spend": "Spend in the first half of the selected period.",
  "later spend": "Spend in the second half of the selected period.",
  "spend change": "How later spend compares with earlier spend. A positive percent means spend rose.",
  conversions: "Actions counted as a result, such as a purchase, a signup, or a form submit. These come from the conversion actions on the account.",
  "conv.": "Conversions. Actions counted as a result, such as a purchase, a signup, or a form submit.",
  "earlier conv.": "Conversions in the first half of the selected period.",
  "later conv.": "Conversions in the second half of the selected period.",
  "conv. change": "How later conversions compare with earlier conversions. A positive percent means conversions rose.",
  cpa: "Cost per action. Spend divided by conversions. A lower CPA means each result cost less.",
  roas: "Return on ad spend. Conversion value divided by spend. A ROAS of 2 means the tracked value was twice the spend.",
  cpc: "Cost per click. Spend divided by clicks.",
  ctr: "Click-through rate. Clicks divided by impressions, the share of times an ad was shown and then clicked.",
  clicks: "Times someone clicked an ad.",
  "impr.": "Impressions. Times an ad was shown.",
  impressions: "Times an ad was shown.",
  "impr. share": "Search impression share. The share of eligible searches where an ad from this channel actually showed.",
  "lost to budget": "The share of eligible impressions missed because the campaign budget ran out.",
  "conversion value": "The money value assigned to the conversions, using the values set on the conversion actions.",
  "conversion rate": "Conversions divided by clicks. The share of clicks that became a counted result.",
};

function explain(label: string) {
  return HELP[label.trim().toLowerCase()] ?? null;
}

export function Term({ children }: { children: string }) {
  const help = explain(children);
  const [box, setBox] = useState<{ left: number; top: number; bottom: number } | null>(null);
  if (!help) return <>{children}</>;

  const placeBelow = box != null && box.top < 96;
  const left = box == null ? 0 : Math.min(Math.max(8, box.left), window.innerWidth - 272);

  return (
    <span
      className="cursor-help underline decoration-dotted decoration-neutral-400 underline-offset-2"
      onMouseEnter={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        setBox({ left: rect.left, top: rect.top, bottom: rect.bottom });
      }}
      onMouseLeave={() => setBox(null)}
    >
      {children}
      {box
        ? createPortal(
            <span
              role="tooltip"
              className="pointer-events-none fixed z-50 w-64 rounded-md bg-ink px-2 py-1.5 text-left text-xs font-normal normal-case leading-5 tracking-normal text-white shadow-md"
              style={{ left, top: placeBelow ? box.bottom + 6 : box.top - 6, transform: placeBelow ? undefined : "translateY(-100%)" }}
            >
              {help}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}
