from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models.food import Restaurant


logger = logging.getLogger(__name__)

MAX_MENU_PAGES = 6
MAX_EXTRACTED_TEXT = 120_000
MAX_IMPORT_TEXT = 250_000
MAX_AI_CHUNK_TEXT = 22_000
AI_CHUNK_OVERLAP = 1_500
MAX_AI_OUTPUT_TOKENS = 12_000
OPENAI_TIMEOUT_SECONDS = 90.0
MENU_PENDING_TIMEOUT_SECONDS = 10 * 60
REQUEST_TIMEOUT = 8.0
MENU_LINK_RE = re.compile(r"\b(menu|food|dinner|lunch|brunch|breakfast)\b", re.I)
MENU_FETCH_HEADERS = {
    "User-Agent": "python-requests/2.32.5",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


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
    target_url = restaurant.menu_url or restaurant.website_uri
    if not target_url:
        logger.info(
            "Restaurant menu refresh skipped without website",
            extra={"restaurant_id": restaurant.id, "restaurant_name": restaurant.name},
        )
        return MenuFetchResult(
            source_url=None,
            extracted_text="",
            structured_json={"items": [], "summary": "No website saved."},
            status="failed",
            error_message="Add a website before fetching the menu.",
        )

    logger.info(
        "Restaurant menu refresh started",
        extra={
            "restaurant_id": restaurant.id,
            "restaurant_name": restaurant.name,
            "website_url": restaurant.website_uri,
            "menu_url": restaurant.menu_url,
            "target_url": target_url,
        },
    )
    extracted = _fetch_menu_text(target_url)
    if not extracted.extracted_text:
        logger.warning(
            "Restaurant menu refresh failed before AI",
            extra={
                "restaurant_id": restaurant.id,
                "restaurant_name": restaurant.name,
                "target_url": target_url,
                "status": extracted.status,
                "error_message": extracted.error_message,
            },
        )
        return extracted
    if not settings.restaurant_ai_enabled:
        return MenuFetchResult(
            source_url=extracted.source_url,
            extracted_text=extracted.extracted_text,
            structured_json=_fallback_structure(restaurant, extracted.extracted_text),
            status="fetched_without_ai",
            error_message="OPENAI_API_KEY is not configured.",
        )
    return MenuFetchResult(
        source_url=extracted.source_url,
        extracted_text=extracted.extracted_text,
        structured_json=_pending_structure("Parsing fetched menu with AI."),
        status="fetch_pending",
    )


def import_menu_text_for_restaurant(
    restaurant: Restaurant, source_url: str | None, extracted_text: str
) -> MenuFetchResult:
    text = _clean_text(extracted_text[:MAX_IMPORT_TEXT])[:MAX_EXTRACTED_TEXT]
    if not text:
        return MenuFetchResult(
            source_url=source_url,
            extracted_text="",
            structured_json={"items": [], "summary": "No menu text imported."},
            status="failed",
            error_message="Imported menu text is empty.",
        )
    if not settings.restaurant_ai_enabled:
        return MenuFetchResult(
            source_url=source_url,
            extracted_text=text,
            structured_json=_fallback_structure(restaurant, text),
            status="imported_without_ai",
            error_message="OPENAI_API_KEY is not configured.",
        )
    return MenuFetchResult(
        source_url=source_url,
        extracted_text=text,
        structured_json=_pending_structure("Parsing imported menu with AI."),
        status="import_pending",
    )


def _fetch_menu_text(website_url: str) -> MenuFetchResult:
    fetch_errors: list[str] = []
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers=MENU_FETCH_HEADERS,
        ) as client:
            first_page = _fetch_page(client, website_url)
            candidate_urls = _menu_candidate_urls(website_url, first_page.links)
            logger.info(
                "Restaurant menu candidate URLs found",
                extra={
                    "website_url": website_url,
                    "candidate_count": len(candidate_urls),
                    "candidate_urls": candidate_urls[:MAX_MENU_PAGES],
                },
            )
            texts: list[str] = []
            source_url = first_page.url
            for url in candidate_urls[:MAX_MENU_PAGES]:
                try:
                    page = first_page if url == first_page.url else _fetch_page(client, url)
                except httpx.HTTPError as exc:
                    message = _http_error_message(exc, url)
                    fetch_errors.append(message)
                    logger.warning(
                        "Restaurant menu candidate fetch failed",
                        extra={"candidate_url": url, "error_message": message},
                    )
                    continue
                logger.info(
                    "Restaurant menu candidate fetched",
                    extra={
                        "candidate_url": url,
                        "resolved_url": page.url,
                        "text_length": len(page.text),
                        "link_count": len(page.links),
                        "accepted": bool(
                            MENU_LINK_RE.search(url) or _looks_like_menu_text(page.text)
                        ),
                    },
                )
                if MENU_LINK_RE.search(url) or _looks_like_menu_text(page.text):
                    source_url = page.url
                    texts.append(page.text)
                if sum(len(text) for text in texts) >= MAX_EXTRACTED_TEXT:
                    break
    except httpx.HTTPError as exc:
        message = _http_error_message(exc, website_url)
        logger.exception(
            "Restaurant menu HTTP fetch failed",
            extra={"website_url": website_url},
        )
        return MenuFetchResult(
            source_url=website_url,
            extracted_text="",
            structured_json={"items": [], "summary": "Menu fetch failed."},
            status="failed",
            error_message=message,
        )

    text = _clean_text("\n".join(texts))[:MAX_EXTRACTED_TEXT]
    if not text:
        error_message = "No menu-like text found on the restaurant website."
        if fetch_errors:
            error_message = f"{error_message} Fetch errors: {'; '.join(fetch_errors[:3])}"
        logger.warning(
            "Restaurant menu fetch found no menu-like text",
            extra={"website_url": website_url, "fetch_errors": fetch_errors},
        )
        return MenuFetchResult(
            source_url=website_url,
            extracted_text="",
            structured_json={"items": [], "summary": "No menu-like text found."},
            status="failed",
            error_message=error_message,
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
    logger.info(
        "Restaurant menu page response received",
        extra={
            "request_url": url,
            "resolved_url": str(response.url),
            "status_code": response.status_code,
            "content_type": content_type,
            "content_length": len(response.content),
        },
    )
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


def _http_error_message(exc: httpx.HTTPError, url: str) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        reason = exc.response.reason_phrase
        message = f"HTTP {status_code} {reason} for {exc.request.url}"
        if status_code == 403:
            return (
                f"{message}. The menu or ordering provider is blocking server-side "
                "fetches, so Command Center cannot read that URL directly."
            )
        return message
    return f"{exc.__class__.__name__} for {url}: {exc}"


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
        source_url=restaurant.menu_url or restaurant.website_uri,
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


def _pending_structure(summary: str) -> dict[str, Any]:
    return {"summary": summary, "items": []}


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

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=OPENAI_TIMEOUT_SECONDS,
    )
    chunks = _chunk_menu_text_for_ai(text)
    structured_chunks = [
        _structure_menu_chunk_with_openai(
            client,
            restaurant,
            chunk,
            chunk_index=index,
            chunk_count=len(chunks),
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    return _merge_structured_menu_chunks(structured_chunks)


def _structure_menu_chunk_with_openai(
    client: Any,
    restaurant: Restaurant,
    ai_text: str,
    chunk_index: int,
    chunk_count: int,
) -> dict[str, Any]:
    prompt = {
        "restaurant": restaurant.custom_name or restaurant.name,
        "instructions": (
            "Extract menu intelligence from this menu text chunk for restaurant "
            "flavor search. Return compact "
            "strict JSON with keys summary and items. Each item must have name, "
            "description, category, flavor_tags, dietary_tags, confidence. Keep "
            "descriptions concise. Include every real menu item visible in this chunk, "
            "including entrees, sides, drinks, desserts, add-ons, modifiers, and "
            "items near the end of the chunk. "
            "but do not invent dishes. If the text is duplicated, deduplicate within "
            "this chunk."
        ),
        "chunk": chunk_index,
        "chunk_count": chunk_count,
        "menu_text": ai_text,
    }
    response = client.responses.create(
        model=settings.openai_restaurant_model,
        input=json.dumps(prompt),
        max_output_tokens=MAX_AI_OUTPUT_TOKENS,
        text={"format": {"type": "json_object"}},
    )
    parsed = _parse_json_output(getattr(response, "output_text", ""))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("OpenAI returned an unexpected menu JSON shape.")
    return parsed


def _chunk_menu_text_for_ai(text: str) -> list[str]:
    prepared = _prepare_menu_text_for_ai(text)
    if len(prepared) <= MAX_AI_CHUNK_TEXT:
        return [prepared]
    if "\n" not in prepared:
        return _chunk_long_text(prepared)
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for line in prepared.splitlines():
        line_size = len(line) + 1
        if line_size > MAX_AI_CHUNK_TEXT:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_size = 0
            chunks.extend(_chunk_long_text(line))
            continue
        if current and current_size + line_size > MAX_AI_CHUNK_TEXT:
            chunks.append("\n".join(current))
            current = []
            current_size = 0
        current.append(line)
        current_size += line_size
    if current:
        chunks.append("\n".join(current))
    return chunks or [prepared[:MAX_AI_CHUNK_TEXT]]


def _chunk_long_text(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_AI_CHUNK_TEXT, len(text))
        if end < len(text):
            boundary = max(
                text.rfind(". ", start, end),
                text.rfind(" | ", start, end),
                text.rfind("  ", start, end),
            )
            if boundary > start + (MAX_AI_CHUNK_TEXT // 2):
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - AI_CHUNK_OVERLAP, 0)
    return [chunk for chunk in chunks if chunk]


def _prepare_menu_text_for_ai(text: str) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for line in re.split(r"[\r\n]+", text):
        clean_line = _clean_text(line)
        if not clean_line or clean_line in seen:
            continue
        seen.add(clean_line)
        lines.append(clean_line)
    if not lines:
        return text
    return "\n".join(lines)


def _merge_structured_menu_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    merged_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    summaries: list[str] = []
    for chunk in chunks:
        summary = str(chunk.get("summary") or "").strip()
        if summary:
            summaries.append(summary)
        for item in chunk.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = _clean_text(str(item.get("name") or ""))
            if not name:
                continue
            key = _menu_item_dedupe_key(name)
            if key in seen:
                continue
            seen.add(key)
            merged_items.append(item)
    return {
        "summary": _merge_menu_summaries(summaries) or "Menu parsed from cached text.",
        "items": merged_items,
    }


def _merge_menu_summaries(summaries: list[str]) -> str:
    sentences: list[str] = []
    seen: set[str] = set()
    for summary in summaries:
        for sentence in re.split(r"(?<=[.!?])\s+", summary):
            clean_sentence = _clean_text(sentence)
            if not clean_sentence:
                continue
            key = re.sub(r"[^a-z0-9]+", " ", clean_sentence.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            sentences.append(clean_sentence)
            if len(" ".join(sentences)) >= 700:
                return " ".join(sentences)[:700].rstrip()
    return " ".join(sentences)[:700].rstrip()


def _menu_item_dedupe_key(name: str) -> str:
    normalized = _clean_text(name).lower()
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    stopwords = {
        "a",
        "an",
        "and",
        "the",
        "with",
        "w",
        "choice",
        "of",
        "add",
        "extra",
    }
    tokens = [token for token in normalized.split() if token not in stopwords]
    return " ".join(tokens)


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
        "summary": cache.error_message
        if cache.status == "failed" and cache.error_message
        else (cache.structured_json or {}).get("summary"),
        "item_count": len((cache.structured_json or {}).get("items") or []),
        "has_data": bool(cache.extracted_text),
        "has_pending_data": bool(cache.pending_extracted_text),
    }


def apply_menu_result(restaurant: Restaurant, result: MenuFetchResult) -> None:
    from app.models.food import RestaurantMenuCache

    cache = restaurant.menu_cache
    now = datetime.utcnow()
    if cache is None:
        cache = RestaurantMenuCache(restaurant=restaurant)
    if result.status.endswith("_pending"):
        cache.pending_source_url = result.source_url
        cache.pending_extracted_text = result.extracted_text
        cache.pending_content_hash = result.content_hash if result.extracted_text else None
        cache.status = result.status
        cache.error_message = None
        if not cache.extracted_text:
            cache.source_url = result.source_url
            cache.extracted_text = result.extracted_text
            cache.structured_json = result.structured_json
            cache.content_hash = result.content_hash if result.extracted_text else None
            cache.fetched_at = now
        cache.updated_at = now
        restaurant.menu_cache = cache
        return
    if result.status == "failed" and cache.extracted_text:
        cache.status = result.status
        cache.error_message = result.error_message
        cache.source_url = result.source_url or cache.source_url
        cache.updated_at = now
        restaurant.menu_cache = cache
        return
    cache.source_url = result.source_url
    cache.extracted_text = result.extracted_text
    cache.structured_json = result.structured_json
    cache.content_hash = result.content_hash if result.extracted_text else None
    cache.status = result.status
    cache.error_message = result.error_message
    cache.fetched_at = now if result.status not in {"failed"} else cache.fetched_at
    if result.extracted_text and _is_successful_menu_status(result.status):
        cache.last_success_status = result.status
        cache.last_success_source_url = result.source_url
        cache.last_success_at = now
        cache.pending_source_url = None
        cache.pending_extracted_text = None
        cache.pending_content_hash = None
    cache.updated_at = now
    restaurant.menu_cache = cache


def queue_menu_ai_structure(restaurant_id: int, success_status: str) -> None:
    thread = threading.Thread(
        target=_structure_menu_background,
        args=(restaurant_id, success_status),
        daemon=True,
    )
    thread.start()


def _structure_menu_background(restaurant_id: int, success_status: str) -> None:
    with SessionLocal() as session:
        restaurant = session.get(Restaurant, restaurant_id)
        if restaurant is None or restaurant.menu_cache is None:
            return
        cache = restaurant.menu_cache
        starting_status = cache.status
        starting_hash = cache.pending_content_hash
        text = cache.pending_extracted_text or cache.extracted_text or ""
        if not text:
            cache.status = "failed"
            cache.error_message = "No menu text was available for AI parsing."
            session.commit()
            return
        try:
            structured_json = _structure_menu_with_openai(restaurant, text)
            final_status = success_status
            error_message = None
        except Exception as exc:
            logger.exception(
                "Restaurant menu background AI structuring failed",
                extra={
                    "restaurant_id": restaurant.id,
                    "restaurant_name": restaurant.name,
                    "source_url": cache.source_url,
                },
            )
            structured_json = _fallback_structure(restaurant, text)
            final_status = _without_ai_status(success_status)
            error_message = f"AI menu structuring failed: {exc}"
        session.refresh(cache)
        if cache.status != starting_status or cache.pending_content_hash != starting_hash:
            logger.info(
                "Discarding stale restaurant menu AI result",
                extra={
                    "restaurant_id": restaurant.id,
                    "restaurant_name": restaurant.name,
                },
            )
            session.rollback()
            return
        now = datetime.utcnow()
        cache.source_url = cache.pending_source_url or cache.source_url
        cache.extracted_text = text
        cache.content_hash = starting_hash
        cache.structured_json = structured_json
        cache.status = final_status
        cache.error_message = error_message
        cache.last_success_status = final_status
        cache.last_success_source_url = cache.source_url
        cache.last_success_at = now
        cache.pending_source_url = None
        cache.pending_extracted_text = None
        cache.pending_content_hash = None
        cache.fetched_at = now
        cache.updated_at = now
        session.commit()


def _is_successful_menu_status(status: str) -> bool:
    return status != "failed" and not status.endswith("_pending")


def _without_ai_status(success_status: str) -> str:
    return {
        "fetched": "fetched_without_ai",
        "imported": "imported_without_ai",
    }.get(success_status, "fetched_without_ai")


def menu_cache_is_pending(restaurant: Restaurant) -> bool:
    cache = restaurant.menu_cache
    return bool(cache and cache.status.endswith("_pending"))


def menu_cache_pending_is_stale(restaurant: Restaurant) -> bool:
    cache = restaurant.menu_cache
    if cache is None or not cache.status.endswith("_pending") or cache.updated_at is None:
        return False
    return (datetime.utcnow() - cache.updated_at).total_seconds() > MENU_PENDING_TIMEOUT_SECONDS


def cancel_menu_parsing(restaurant: Restaurant) -> bool:
    cache = restaurant.menu_cache
    if cache is None or not cache.status.endswith("_pending"):
        return False
    cache.status = cache.last_success_status or ("cached" if cache.extracted_text else "canceled")
    cache.error_message = None
    if cache.last_success_source_url:
        cache.source_url = cache.last_success_source_url
    if cache.last_success_at:
        cache.fetched_at = cache.last_success_at
    cache.pending_source_url = None
    cache.pending_extracted_text = None
    cache.pending_content_hash = None
    cache.updated_at = datetime.utcnow()
    return True


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
        evidence: list[dict[str, Any]] = []
        score = 0
        searchable_parts = [candidate.get("summary") or ""]
        for item in candidate["items"]:
            if not isinstance(item, dict):
                continue
            item_parts = [
                str(item.get("name") or ""),
                str(item.get("description") or ""),
                " ".join(str(tag) for tag in item.get("flavor_tags") or []),
                " ".join(str(tag) for tag in item.get("dietary_tags") or []),
            ]
            searchable_parts.extend(
                item_parts
            )
            item_text = " ".join(item_parts).lower()
            matched_terms = sorted(term for term in query_terms if term in item_text)
            if normalized_query in item_text:
                matched_terms.append(normalized_query)
            if matched_terms:
                evidence.append(
                    {
                        "name": item.get("name"),
                        "description": item.get("description"),
                        "flavor_tags": item.get("flavor_tags") or [],
                        "matched_terms": sorted(set(matched_terms)),
                    }
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
                    "reason": _menu_match_reason(candidate, evidence, matches),
                    "matched_terms": matches[:5],
                    "evidence": evidence[:5],
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
            "Use only the supplied candidates and their evidence. The reason should "
            "be one concise plain-English sentence grounded in specific dishes, "
            "descriptions, or flavor tags. Do not use generic boilerplate like "
            "'menu match for the craving term'. Do not invent menu items."
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


def _menu_match_reason(
    candidate: dict[str, Any],
    evidence: list[dict[str, Any]],
    matches: list[str],
) -> str:
    if evidence:
        item_names = [
            str(item.get("name")).strip()
            for item in evidence
            if str(item.get("name") or "").strip()
        ][:3]
        tags = sorted(
            {
                str(tag).strip()
                for item in evidence
                for tag in item.get("flavor_tags", [])
                if str(tag).strip()
            }
        )[:4]
        if item_names and tags:
            return (
                f"Menu evidence includes {', '.join(item_names)} with "
                f"{', '.join(tags)} flavors."
            )
        if item_names:
            return f"Menu evidence includes {', '.join(item_names)}."
    summary = str(candidate.get("summary") or "").strip()
    if summary:
        return summary[:180]
    return f"Cached menu includes {', '.join(matches[:5])}."


def _parse_json_output(output_text: str) -> dict[str, Any]:
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed
