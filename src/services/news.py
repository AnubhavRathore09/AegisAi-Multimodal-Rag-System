from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NEWS_ENDPOINT = "https://newsdata.io/api/1/latest"


def _normalize_articles(payload: dict) -> list[dict]:
    results = payload.get("results")
    if isinstance(results, list):
        return results
    return []


def get_live_news(query: str) -> str:
    api_key = os.getenv("NEWSDATA_API_KEY", "").strip()
    clean_query = str(query or "").strip()
    if not clean_query or not api_key:
        return "No latest data available"

    enriched_query = f"{clean_query} latest news"
    params = {
        "apikey": api_key,
        "q": enriched_query,
        "language": "en",
    }
    url = f"{NEWS_ENDPOINT}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "AegisAI/1.0"})

    try:
        with urlopen(request, timeout=12) as response:
            raw_text = response.read().decode("utf-8")
    except Exception as exc:
        print("NEWS RAW RESPONSE:", f"request_failed: {exc}")
        return "No latest data available"

    print("NEWS RAW RESPONSE:", raw_text[:1000])

    try:
        payload = json.loads(raw_text)
    except Exception:
        return "No latest data available"

    articles = _normalize_articles(payload)
    if not articles:
        return "No latest data available"

    lines: list[str] = []
    for article in articles[:3]:
        title = str(article.get("title") or "Untitled").strip()
        description = str(article.get("description") or article.get("content") or "No description available.").strip()
        lines.append(f"Title: {title}\nDescription: {description}")

    return "\n\n".join(lines) if lines else "No latest data available"
