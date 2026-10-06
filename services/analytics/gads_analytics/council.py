from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx
from gads.config import get_settings

from gads_analytics.narrative import load_system_prompt

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class CouncilRateLimited(RuntimeError):
    """Every council model refused because the account is out of requests."""


def council_models() -> list[str]:
    settings = get_settings()
    models = [item.strip() for item in settings.council_models.split(",") if item.strip()]
    return models


def parse_ranking(ranking_text: str) -> list[str]:
    section = ranking_text
    if "FINAL RANKING:" in ranking_text:
        section = ranking_text.split("FINAL RANKING:", 1)[1]
        numbered = re.findall(r"\d+\.\s*Response [A-Z]", section)
        if numbered:
            return [match.group() for item in numbered if (match := re.search(r"Response [A-Z]", item))]
    return re.findall(r"Response [A-Z]", section)


def aggregate_rankings(rankings: list[dict], label_to_model: dict[str, str]) -> list[dict]:
    positions: dict[str, list[int]] = defaultdict(list)
    for ranking in rankings:
        for place, label in enumerate(parse_ranking(ranking["ranking"]), start=1):
            model = label_to_model.get(label)
            if model:
                positions[model].append(place)
    aggregate = [
        {"model": model, "average_rank": round(sum(places) / len(places), 2)}
        for model, places in positions.items()
        if places
    ]
    aggregate.sort(key=lambda item: item["average_rank"])
    return aggregate


def run_council(question: str, report: dict, api_key: str | None = None) -> dict:
    settings = get_settings()
    key = settings.openrouter_api_key if api_key is None else api_key
    models = council_models()
    grounded = (
        f"{load_system_prompt()}\n\nQuestion: {question}\n\n"
        "Use only this JSON. Do not invent metrics.\n"
        + json.dumps(report, default=str)
    )
    opinions = _query_many(models, [{"role": "user", "content": grounded}], key)
    stage1 = [{"model": model, "response": text} for model, text, _error in opinions if text]
    if not stage1:
        if opinions and all(error == "rate_limit" for _model, _text, error in opinions):
            raise CouncilRateLimited("The council models are out of requests for now.")
        raise RuntimeError("No council model answered")

    labels = [chr(65 + index) for index in range(len(stage1))]
    label_to_model = {f"Response {label}": item["model"] for label, item in zip(labels, stage1, strict=True)}
    responses_text = "\n\n".join(f"Response {label}:\n{item['response']}" for label, item in zip(labels, stage1, strict=True))
    ranking_prompt = (
        f"You are evaluating different responses to this question:\n\nQuestion: {question}\n\n"
        f"Here are the anonymized responses:\n\n{responses_text}\n\n"
        "Evaluate each response. At the end, rank them exactly like this:\n"
        "FINAL RANKING:\n1. Response A\n2. Response B\n"
        "List the best response first. Do not add commentary inside the ranking."
    )
    ranking_models = [item["model"] for item in stage1]
    ranking_answers = _query_many(
        ranking_models,
        [{"role": "user", "content": ranking_prompt}],
        key,
    )
    stage2 = [{"model": model, "ranking": text} for model, text, _error in ranking_answers if text]
    rankings = aggregate_rankings(stage2, label_to_model)

    stage1_text = "\n\n".join(f"Model: {item['model']}\nResponse: {item['response']}" for item in stage1)
    stage2_text = "\n\n".join(f"Model: {item['model']}\nRanking: {item['ranking']}" for item in stage2)
    chairman_prompt = (
        "You are the chairman of an LLM council. Several models answered a Google Ads question from the same data, "
        "then ranked each other. Write one final answer in Markdown, with headings, short paragraphs, and lists. "
        "Use only metrics that appear in their answers. Do not invent numbers.\n\n"
        f"Original question: {question}\n\nIndividual answers:\n{stage1_text}\n\nPeer rankings:\n{stage2_text}"
    )
    chairman_model = settings.chairman_model.strip() or ranking_models[0]
    chairman, _error = _query_one(chairman_model, [{"role": "user", "content": chairman_prompt}], key)
    if not chairman:
        chairman = stage1[0]["response"]
        chairman_model = stage1[0]["model"]
    return {
        "answer": chairman,
        "council": {
            "chairman": chairman_model,
            "opinions": stage1,
            "rankings": rankings,
        },
    }


def complete_one(question: str, report: dict, api_key: str, model: str) -> str:
    """One OpenRouter completion, used when the free council models are out of requests."""
    grounded = (
        f"{load_system_prompt()}\n\nQuestion: {question}\n\n"
        "Use only this JSON. Do not invent metrics.\n"
        + json.dumps(report, default=str)
    )
    text, error = _query_one(model, [{"role": "user", "content": grounded}], api_key)
    if error == "rate_limit":
        raise CouncilRateLimited("The backup model is out of requests.")
    if not text:
        raise RuntimeError("Backup model did not answer")
    return text


def _query_many(models: list[str], messages: list[dict], api_key: str) -> list[tuple[str, str | None, str | None]]:
    if not models:
        return []
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        return list(pool.map(lambda model: (model, *_query_one(model, messages, api_key)), models))


def _message_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return ""


def _query_one(model: str, messages: list[dict], api_key: str) -> tuple[str | None, str | None]:
    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages},
            timeout=120,
        )
        if response.status_code == 429:
            return None, "rate_limit"
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        text = _message_text(message.get("content")) or _message_text(message.get("reasoning"))
    except (httpx.HTTPError, KeyError, IndexError, TypeError):
        return None, "error"
    return (text or None), None
