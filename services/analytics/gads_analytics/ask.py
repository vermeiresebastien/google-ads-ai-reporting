from __future__ import annotations

import json
from datetime import date

import httpx
from gads.config import get_settings
from gads.models import AdAccount
from sqlalchemy.orm import Session

from gads_analytics.council import CouncilRateLimited, complete_one, run_council
from gads_analytics.narrative import load_system_prompt, render_report, tools_for_question
from gads_analytics.repository import build_report
from gads_analytics.trends import build_trends, strategy_context

STRATEGY_PREFACE = (
    "This is a long-term strategic question about the whole selected period. "
    "The JSON compares the earlier half of that period with the later half and includes a weekly series. "
    "It is not a day-to-day report. "
    "Write a long-term overview in Markdown, then answer the question. "
    "State the period. Separate what the numbers show from what they only suggest. "
    "Name the campaigns that drive the move. "
    "Recommend a strategic direction only when the evidence is enough. "
    "Do not invent metrics and do not give a single-day action plan.\n\n"
)


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


def _model_answer(question: str, report: dict) -> tuple[str | None, str, dict | None, str | None, str | None]:
    """Ask the council. If that key is out of requests, try the backup key, then OpenAI.

    Returns answer, model name, council, error code, and a short notice.
    """
    settings = get_settings()
    council_limited = False
    keys = []
    backup_key = getattr(settings, "openrouter_backup_api_key", "")
    for api_key in (settings.openrouter_api_key, backup_key):
        if api_key and api_key not in keys:
            keys.append(api_key)
    for api_key in keys:
        try:
            council_result = run_council(question, report, api_key=api_key)
            return council_result["answer"], "llm-council", council_result["council"], None, None
        except CouncilRateLimited:
            council_limited = True
            continue
        except Exception as exc:
            return None, "deterministic", None, exc.__class__.__name__, None
    if council_limited and backup_key:
        model_name = _openrouter_model(getattr(settings, "openai_model", "") or "gpt-4.1-mini")
        try:
            return complete_one(question, report, backup_key, model_name), model_name, None, None, None
        except CouncilRateLimited:
            pass
        except Exception as exc:
            if not settings.openai_api_key:
                return None, "deterministic", None, exc.__class__.__name__, None
    if council_limited and not settings.openai_api_key:
        return None, "deterministic", None, "rate_limit", _limit_notice(False)
    if settings.openai_api_key and (council_limited or not settings.openrouter_api_key):
        try:
            return _call_openai(question, report), settings.openai_model, None, None, None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                notice = _limit_notice(True) if council_limited else "The model account has no credits left."
                return None, "deterministic", None, "rate_limit", notice
            return None, "deterministic", None, f"http_{exc.response.status_code}", None
        except Exception as exc:
            return None, "deterministic", None, exc.__class__.__name__, None
    return None, "deterministic", None, None, None


def _openrouter_model(name: str) -> str:
    model = name.strip() or "gpt-4.1-mini"
    if "/" not in model:
        return f"openai/{model}"
    return model


def _limit_notice(openai_also_limited: bool) -> str:
    if openai_also_limited:
        return "The council models are out of requests, and the backup model account has no credits left."
    return "The council models are out of requests for now."


def answer_question(session: Session, account: AdAccount, question: str, as_of: date | None) -> dict:
    tools = tools_for_question(question)
    kind = "last_7_vs_prev_7" if "compare" in tools and "daily_report" not in tools else "yesterday_vs_prev7_avg"
    text = question.lower()
    if "quarter" in text:
        kind = "quarter_to_date_vs_prev"
    elif "month" in text:
        kind = "month_to_date_vs_prev"
    elif "90" in text or "history" in text:
        kind = "last_90_vs_prev_90"
    elif "today" in text or ("yesterday" in text and "change" in text):
        kind = "today_vs_yesterday"
    elif "week" in text and "yesterday" not in text:
        kind = "last_7_vs_prev_7"
    report = build_report(session, account, kind, as_of)
    narrative = render_report(report)
    answer, model, council, llm_error, notice = _model_answer(question, report)
    if answer is None:
        if llm_error:
            reason = notice or "The model did not answer."
            answer = f"Question: {question}\n\n{reason} This is the calculated report.\n\n{narrative}"
        else:
            answer = narrative
        model = "deterministic"
        council = None
    return {
        "question": question,
        "answer": answer,
        "model": model,
        "llm_error": llm_error,
        "tools": sorted(tools),
        "report": report,
        "council": council,
        "notice": notice,
    }


def answer_strategy(session: Session, account: AdAccount, question: str, start: date, end: date) -> dict:
    context = strategy_context(build_trends(session, account, start, end))
    overview = "\n".join(context["findings"]) or "No daily stats are stored for this period."
    framed = STRATEGY_PREFACE + question
    answer, model, council, llm_error, notice = _model_answer(framed, context)
    if answer is None:
        if llm_error:
            reason = notice or "The model did not answer."
            answer = f"Question: {question}\n\n{reason} This is the calculated long-term overview.\n\n{overview}"
        else:
            answer = overview
        model = "deterministic"
        council = None
    return {
        "question": question,
        "answer": answer,
        "model": model,
        "llm_error": llm_error,
        "council": council,
        "notice": notice,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
