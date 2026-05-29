from __future__ import annotations

import hashlib
import json
import re
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.models.food import Restaurant


MAX_MENU_PAGES = 6
MAX_EXTRACTED_TEXT = 120_000
REQUEST_TIMEOUT = 8.0
MENU_LINK_RE = re.compile(r"\b(menu|food|dinner|lunch|brunch|breakfast)\b", re.I)


@dataclass(frozen=True)
class MenuFetchResult:
    source_url: str | None
    extracted_text: str
    structured_json: dict[str, Any]
    status: str = "fetched"
    error_message: str | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.extracted_text.encode("utf-8")).hexdigest()


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._parts: list[str] = []
        self._skip_depth = 0
        self._current_link: str | None = None
        self._current_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._current_link = href
                self._current_link_text = []
        if tag in {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "div"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "a" and self._current_link:
            self.links.append((self._current_link, " ".join(self._current_link_text)))
            self._current_link = None
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self._parts.append(text)
        if self._current_link:
            self._current_link_text.append(text)

    @property
    def text(self) -> str:
        return _clean_text(" ".join(self._parts))


def refresh_menu_for_restaurant(restaurant: Restaurant) -> MenuFetchResult:
    if not settings.is_production:
        return _mock_menu_result(restaurant)
    if not restaurant.website_uri:
        return MenuFetchResult(
            source_url=None,
            extracted_text="",
            structured_json={"items": [], "summary": "No website saved."},
            status="failed",
            error_message="Add a website before fetching the menu.",
        )

    extracted = _fetch_menu_text(restaurant.website_uri)
    if not extracted.extracted_text:
        return extracted
    if not settings.restaurant_ai_enabled:
        return MenuFetchResult(
            source_url=extracted.source_url,
            extracted_text=extracted.extracted_text,
            structured_json=_fallback_structure(restaurant, extracted.extracted_text),
            status="fetched_without_ai",
            error_message="OPENAI_API_KEY is not configured.",
        )
    try:
        structured_json = _structure_menu_with_openai(
            restaurant, extracted.extracted_text
        )
    except Exception as exc:
        return MenuFetchResult(
            source_url=extracted.source_url,
            extracted_text=extracted.extracted_text,
            structured_json=_fallback_structure(restaurant, extracted.extracted_text),
            status="fetched_without_ai",
            error_message=f"AI menu structuring failed: {exc}",
        )
    return MenuFetchResult(
        source_url=extracted.source_url,
        extracted_text=extracted.extracted_text,
        structured_json=structured_json,
        status="fetched",
    )


def _fetch_menu_text(website_url: str) -> MenuFetchResult:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "CommandCenterMenuFetcher/1.0"},
        ) as client:
            first_page = _fetch_page(client, website_url)
            candidate_urls = _menu_candidate_urls(website_url, first_page.links)
            texts: list[str] = []
            source_url = first_page.url
            for url in candidate_urls[:MAX_MENU_PAGES]:
                page = first_page if url == first_page.url else _fetch_page(client, url)
                if MENU_LINK_RE.search(url) or _looks_like_menu_text(page.text):
                    source_url = page.url
                    texts.append(page.text)
                if sum(len(text) for text in texts) >= MAX_EXTRACTED_TEXT:
                    break
    except httpx.HTTPError as exc:
        return MenuFetchResult(
            source_url=website_url,
            extracted_text="",
            structured_json={"items": [], "summary": "Menu fetch failed."},
            status="failed",
            error_message=str(exc),
        )

    text = _clean_text("\n".join(texts))[:MAX_EXTRACTED_TEXT]
    if not text:
        return MenuFetchResult(
            source_url=website_url,
            extracted_text="",
            structured_json={"items": [], "summary": "No menu-like text found."},
            status="failed",
            error_message="No menu-like text found on the restaurant website.",
        )
    return MenuFetchResult(
        source_url=source_url,
        extracted_text=text,
        structured_json={},
    )


@dataclass(frozen=True)
class _FetchedPage:
    url: str
    text: str
    links: list[tuple[str, str]]


def _fetch_page(client: httpx.Client, url: str) -> _FetchedPage:
    response = client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "application/pdf" in content_type or str(response.url).lower().endswith(".pdf"):
        return _FetchedPage(str(response.url), _extract_pdf_text(response.content), [])
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return _FetchedPage(str(response.url), "", [])
    parser = _ReadableHtmlParser()
    parser.feed(response.text)
    return _FetchedPage(str(response.url), parser.text, parser.links)


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    reader = PdfReader(BytesIO(content))
    parts = [page.extract_text() or "" for page in reader.pages[:8]]
    return _clean_text("\n".join(parts))


def _menu_candidate_urls(base_url: str, links: list[tuple[str, str]]) -> list[str]:
    parsed_base = urlparse(base_url)
    candidates = [base_url]
    for href, label in links:
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc != parsed_base.netloc:
            continue
        if MENU_LINK_RE.search(f"{label} {parsed.path}"):
            candidates.append(absolute)
    seen: set[str] = set()
    deduped: list[str] = []
    for url in candidates:
        clean_url = url.split("#", 1)[0]
        if clean_url not in seen:
            seen.add(clean_url)
            deduped.append(clean_url)
    return deduped


def _looks_like_menu_text(text: str) -> bool:
    lowered = text.lower()
    signals = ["menu", "appetizer", "entree", "dish", "salad", "sandwich", "dessert"]
    return sum(1 for signal in signals if signal in lowered) >= 2


def _mock_menu_result(restaurant: Restaurant) -> MenuFetchResult:
    name = restaurant.custom_name or restaurant.name
    flavor_source = " ".join(
        value
        for value in [
            restaurant.cuisine or "",
            restaurant.tags or "",
            restaurant.notes or "",
            restaurant.price_level or "",
        ]
        if value
    )
    extracted_text = _clean_text(
        f"{name} development menu. {flavor_source} "
        "Sample dishes include smoky grilled vegetables, crispy noodles, "
        "bright herbs, savory rice bowls, and a simple dessert."
    )
    structured = {
        "summary": "Development mock menu generated without AI.",
        "items": [
            {
                "name": "Smoky grilled vegetables",
                "description": "Mock dish for flavor search testing.",
                "category": "Main",
                "flavor_tags": ["smoky", "grilled", "savory"],
                "dietary_tags": ["vegetarian"],
                "confidence": 0.4,
            },
            {
                "name": "Crispy noodles",
                "description": "Mock dish for flavor search testing.",
                "category": "Main",
                "flavor_tags": ["crispy", "savory"],
                "dietary_tags": [],
                "confidence": 0.4,
            },
        ],
    }
    return MenuFetchResult(
        source_url=restaurant.website_uri,
        extracted_text=extracted_text,
        structured_json=structured,
        status="mocked",
    )


def _fallback_structure(restaurant: Restaurant, text: str) -> dict[str, Any]:
    return {
        "summary": "Menu text fetched but AI structuring is disabled.",
        "items": [
            {
                "name": restaurant.custom_name or restaurant.name,
                "description": text[:500],
                "category": "Menu",
                "flavor_tags": _simple_tags(text),
                "dietary_tags": [],
                "confidence": 0.2,
            }
        ],
    }


def _simple_tags(text: str) -> list[str]:
    tags = [
        "smoky",
        "spicy",
        "crispy",
        "sweet",
        "savory",
        "fresh",
        "grilled",
        "fried",
        "comforting",
    ]
    lowered = text.lower()
    return [tag for tag in tags if tag in lowered]


def _structure_menu_with_openai(restaurant: Restaurant, text: str) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the openai package before using production AI.") from exc

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = {
        "restaurant": restaurant.custom_name or restaurant.name,
        "instructions": (
            "Extract menu intelligence for restaurant flavor search. Return only JSON "
            "with keys summary and items. Each item must have name, description, "
            "category, flavor_tags, dietary_tags, confidence. Do not invent dishes."
        ),
        "menu_text": text,
    }
    response = client.responses.create(
        model=settings.openai_restaurant_model,
        input=json.dumps(prompt),
    )
    parsed = _parse_json_output(getattr(response, "output_text", ""))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("OpenAI returned an unexpected menu JSON shape.")
    return parsed


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def menu_cache_payload(restaurant: Restaurant) -> dict[str, Any] | None:
    cache = restaurant.menu_cache
    if cache is None:
        return None
    return {
        "status": cache.status,
        "source_url": cache.source_url,
        "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
        "error_message": cache.error_message,
        "summary": (cache.structured_json or {}).get("summary"),
        "item_count": len((cache.structured_json or {}).get("items") or []),
    }


def apply_menu_result(restaurant: Restaurant, result: MenuFetchResult) -> None:
    from app.models.food import RestaurantMenuCache

    cache = restaurant.menu_cache
    now = datetime.utcnow()
    if cache is None:
        cache = RestaurantMenuCache(restaurant=restaurant)
    cache.source_url = result.source_url
    cache.extracted_text = result.extracted_text
    cache.structured_json = result.structured_json
    cache.content_hash = result.content_hash if result.extracted_text else None
    cache.status = result.status
    cache.error_message = result.error_message
    cache.fetched_at = now if result.status not in {"failed"} else cache.fetched_at
    cache.updated_at = now
    restaurant.menu_cache = cache


def search_restaurant_menus(
    restaurants: list[Restaurant], query: str
) -> list[dict[str, Any]]:
    normalized_query = _clean_text(query).lower()
    if not normalized_query:
        return []

    candidates = [
        _restaurant_search_candidate(restaurant)
        for restaurant in restaurants
        if restaurant.menu_cache and restaurant.menu_cache.structured_json
    ]
    if not candidates:
        return []

    simple_results = _simple_menu_search(candidates, normalized_query)
    if not settings.restaurant_ai_enabled:
        return simple_results[:8]
    return _rerank_menu_search_with_openai(normalized_query, simple_results[:12])


def _restaurant_search_candidate(restaurant: Restaurant) -> dict[str, Any]:
    cache = restaurant.menu_cache
    structured = cache.structured_json if cache else {}
    items = structured.get("items") if isinstance(structured, dict) else []
    if not isinstance(items, list):
        items = []
    return {
        "restaurant_id": restaurant.id,
        "name": restaurant.custom_name or restaurant.name,
        "summary": structured.get("summary") if isinstance(structured, dict) else "",
        "items": items,
    }


def _simple_menu_search(
    candidates: list[dict[str, Any]], normalized_query: str
) -> list[dict[str, Any]]:
    query_terms = {
        term for term in re.split(r"[^a-z0-9]+", normalized_query) if len(term) > 2
    }
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        matches: list[str] = []
        score = 0
        searchable_parts = [candidate.get("summary") or ""]
        for item in candidate["items"]:
            if not isinstance(item, dict):
                continue
            searchable_parts.extend(
                [
                    str(item.get("name") or ""),
                    str(item.get("description") or ""),
                    " ".join(str(tag) for tag in item.get("flavor_tags") or []),
                    " ".join(str(tag) for tag in item.get("dietary_tags") or []),
                ]
            )
        searchable = " ".join(searchable_parts).lower()
        for term in query_terms:
            if term in searchable:
                score += 2
                matches.append(term)
        if normalized_query in searchable:
            score += 4
        if score:
            results.append(
                {
                    "restaurant_id": candidate["restaurant_id"],
                    "name": candidate["name"],
                    "score": score,
                    "reason": f"Cached menu matches: {', '.join(matches[:5])}.",
                    "matched_terms": matches[:5],
                }
            )
    return sorted(results, key=lambda result: result["score"], reverse=True)


def _rerank_menu_search_with_openai(
    normalized_query: str, simple_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not simple_results:
        return []
    try:
        from openai import OpenAI
    except ImportError:
        return simple_results

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = {
        "instructions": (
            "Rerank saved restaurant menu search results for the user's craving. "
            "Return only JSON with key results. Each result must include "
            "restaurant_id, name, score from 0 to 1, reason, matched_terms. "
            "Use only the supplied candidates."
        ),
        "query": normalized_query,
        "candidates": simple_results,
    }
    try:
        response = client.responses.create(
            model=settings.openai_restaurant_model,
            input=json.dumps(prompt),
        )
        parsed = _parse_json_output(getattr(response, "output_text", ""))
    except Exception:
        return simple_results
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list):
        return simple_results
    return results[:8]


def _parse_json_output(output_text: str) -> dict[str, Any]:
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed
