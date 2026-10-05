from __future__ import annotations

import json
from datetime import date

import httpx
from gads.config import get_settings
from gads.models import AdAccount
from sqlalchemy.orm import Session

from gads_analytics.narrative import load_system_prompt, render_report, tools_for_question
from gads_analytics.repository import build_report


def _call_openai(question: str, report: dict) -> str:
    settings = get_settings()
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.openai_model,
            "input": [
                {"role": "system", "content": load_system_prompt()},
                {
                    "role": "user",
                    "content": (
                        f"{question}\n\nUse only this JSON. Do not invent metrics.\n"
                        + json.dumps(report, default=str)
                    ),
                },
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("output_text"):
        return payload["output_text"]
    texts = []
    for item in payload.get("output", []):
        for content in item.get("content") or []:
            text = content.get("text")
            if text:
                texts.append(text)
    if not texts:
        raise RuntimeError("OpenAI response did not include text")
    return "\n".join(texts)


def answer_question(session: Session, account: AdAccount, question: str, as_of: date | None) -> dict:
    tools = tools_for_question(question)
    kind = "last_7_vs_prev_7" if "compare" in tools and "daily_report" not in tools else "yesterday_vs_prev7_avg"
    if "week" in question.lower() and "yesterday" not in question.lower():
        kind = "last_7_vs_prev_7"
    report = build_report(session, account, kind, as_of)
    narrative = render_report(report)
    model = "deterministic"
    llm_error = None
    answer = narrative
    settings = get_settings()
    if settings.openai_api_key:
        try:
            answer = _call_openai(question, report)
            model = settings.openai_model
        except Exception as exc:
            llm_error = exc.__class__.__name__
    return {
        "question": question,
        "answer": answer,
        "model": model,
        "llm_error": llm_error,
        "tools": sorted(tools),
        "report": report,
    }
