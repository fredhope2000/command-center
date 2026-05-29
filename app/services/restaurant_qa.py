from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.models.food import Restaurant
from app.services.restaurant_menus import _parse_json_output


MAX_CANDIDATES_FOR_AI = 8
MAX_MENU_ITEMS_PER_RESTAURANT = 8
MAX_NOTE_LENGTH = 700
MAX_DESCRIPTION_LENGTH = 280

STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "best",
    "can",
    "could",
    "did",
    "does",
    "for",
    "from",
    "good",
    "have",
    "how",
    "like",
    "near",
    "our",
    "place",
    "places",
    "restaurant",
    "restaurants",
    "should",
    "that",
    "the",
    "there",
    "this",
    "what",
    "where",
    "which",
    "with",
    "would",
}


def answer_restaurant_question(
    restaurants: list[Restaurant], question: str
) -> dict[str, Any]:
    cleaned_question = _clean_text(question)
    if not cleaned_question:
        raise ValueError("Question is required.")

    candidates = _rank_restaurant_candidates(restaurants, cleaned_question)
    selected = candidates[:MAX_CANDIDATES_FOR_AI]
    if settings.restaurant_ai_enabled and selected:
        ai_answer = _answer_with_openai(cleaned_question, selected)
        if ai_answer is not None:
            return ai_answer

    return _fallback_answer(cleaned_question, selected)


def _rank_restaurant_candidates(
    restaurants: list[Restaurant], question: str
) -> list[dict[str, Any]]:
    query_terms = _query_terms(question)
    broad_ranking = _looks_like_broad_ranking(question)
    candidates: list[dict[str, Any]] = []
    for restaurant in restaurants:
        context = _restaurant_context(restaurant)
        searchable = _searchable_text(context)
        matched_terms = sorted(term for term in query_terms if term in searchable)
        score = len(matched_terms) * 4
        if restaurant.personal_rating:
            score += restaurant.personal_rating
        if restaurant.status.value == "visited":
            score += 2
        if broad_ranking and restaurant.personal_rating:
            score += restaurant.personal_rating * 2
        if matched_terms or (
            broad_ranking
            and (restaurant.personal_rating or restaurant.status.value == "visited")
        ):
            context["score"] = score
            context["matched_terms"] = matched_terms
            candidates.append(context)

    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate["score"],
            -(candidate.get("personal_rating") or 0),
            candidate["name"],
        ),
    )


def _restaurant_context(restaurant: Restaurant) -> dict[str, Any]:
    structured = {}
    if restaurant.menu_cache and isinstance(restaurant.menu_cache.structured_json, dict):
        structured = restaurant.menu_cache.structured_json
    menu_items = structured.get("items") if isinstance(structured, dict) else []
    if not isinstance(menu_items, list):
        menu_items = []

    return {
        "restaurant_id": restaurant.id,
        "name": restaurant.custom_name or restaurant.name,
        "google_name": restaurant.name,
        "status": restaurant.status.value,
        "category": restaurant.category.value if restaurant.category else None,
        "cuisine": restaurant.cuisine,
        "tags": restaurant.tags,
        "neighborhood": restaurant.neighborhood,
        "personal_rating": restaurant.personal_rating,
        "price_level": restaurant.price_level,
        "notes": _clip(restaurant.notes, MAX_NOTE_LENGTH),
        "address": restaurant.formatted_address,
        "menu_summary": _clip(structured.get("summary"), MAX_DESCRIPTION_LENGTH),
        "menu_items": [
            {
                "name": _clip(item.get("name"), 120),
                "description": _clip(item.get("description"), MAX_DESCRIPTION_LENGTH),
                "flavor_tags": item.get("flavor_tags") or [],
                "dietary_tags": item.get("dietary_tags") or [],
            }
            for item in menu_items[:MAX_MENU_ITEMS_PER_RESTAURANT]
            if isinstance(item, dict)
        ],
    }


def _answer_with_openai(
    question: str, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = {
        "instructions": (
            "Answer the user's restaurant question using only the supplied saved "
            "restaurant database context. If the data is insufficient, say that. "
            "Do not invent hours, availability, current menu facts, dietary claims, "
            "or visits. Return strict JSON with keys answer and results. Results "
            "must contain restaurant_id, name, reason, and evidence. Keep the answer "
            "concise and grounded in saved notes, ratings, categories, tags, cuisine, "
            "neighborhood, or menu items."
        ),
        "question": question,
        "restaurants": candidates,
    }
    try:
        response = client.responses.create(
            model=settings.openai_restaurant_model,
            input=json.dumps(prompt),
            text={"format": {"type": "json_object"}},
        )
        parsed = _parse_json_output(getattr(response, "output_text", ""))
    except Exception:
        return None

    answer = parsed.get("answer")
    results = parsed.get("results")
    if not isinstance(answer, str) or not isinstance(results, list):
        return None
    return {
        "answer": answer.strip(),
        "results": [
            _clean_ai_result(result)
            for result in results
            if isinstance(result, dict)
        ][:MAX_CANDIDATES_FOR_AI],
        "source": "ai",
    }


def _fallback_answer(question: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {
            "answer": (
                "I could not find enough saved restaurant data to answer that from "
                "the database."
            ),
            "results": [],
            "source": "local",
        }

    results = [_fallback_result(candidate) for candidate in candidates[:5]]
    names = ", ".join(result["name"] for result in results[:3])
    if len(results) == 1:
        answer = f"The best saved match I found is {names}."
    else:
        answer = f"The strongest saved matches I found are {names}."
    return {"answer": answer, "results": results, "source": "local"}


def _fallback_result(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = _candidate_evidence(candidate)
    reason_parts = []
    if candidate.get("personal_rating"):
        reason_parts.append(f"{candidate['personal_rating']}/5")
    for key in ("cuisine", "neighborhood", "category", "tags"):
        value = candidate.get(key)
        if value:
            reason_parts.append(str(value).replace("_", " "))
    if candidate.get("matched_terms"):
        reason_parts.append(f"matches {', '.join(candidate['matched_terms'][:4])}")
    reason = "; ".join(reason_parts) or "Saved restaurant match"
    return {
        "restaurant_id": candidate["restaurant_id"],
        "name": candidate["name"],
        "reason": reason,
        "evidence": evidence,
    }


def _candidate_evidence(candidate: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    if candidate.get("notes"):
        evidence.append(f"Notes: {candidate['notes']}")
    if candidate.get("menu_summary"):
        evidence.append(f"Menu: {candidate['menu_summary']}")
    for item in candidate.get("menu_items") or []:
        name = item.get("name")
        description = item.get("description")
        if name and description:
            evidence.append(f"{name}: {description}")
        elif name:
            evidence.append(str(name))
        if len(evidence) >= 3:
            break
    return evidence


def _clean_ai_result(result: dict[str, Any]) -> dict[str, Any]:
    evidence = result.get("evidence")
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    return {
        "restaurant_id": result.get("restaurant_id"),
        "name": str(result.get("name") or "Restaurant"),
        "reason": str(result.get("reason") or "").strip(),
        "evidence": [str(item) for item in evidence[:4] if str(item).strip()],
    }


def _searchable_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("name"),
        candidate.get("google_name"),
        candidate.get("status"),
        candidate.get("category"),
        candidate.get("cuisine"),
        candidate.get("tags"),
        candidate.get("neighborhood"),
        candidate.get("price_level"),
        candidate.get("notes"),
        candidate.get("address"),
        candidate.get("menu_summary"),
    ]
    for item in candidate.get("menu_items") or []:
        parts.extend(
            [
                item.get("name"),
                item.get("description"),
                " ".join(str(tag) for tag in item.get("flavor_tags") or []),
                " ".join(str(tag) for tag in item.get("dietary_tags") or []),
            ]
        )
    return _clean_text(" ".join(str(part) for part in parts if part)).lower()


def _query_terms(question: str) -> set[str]:
    return {
        term
        for term in re.split(r"[^a-z0-9]+", question.lower())
        if len(term) > 2 and term not in STOP_WORDS
    }


def _looks_like_broad_ranking(question: str) -> bool:
    lowered = question.lower()
    return any(
        phrase in lowered
        for phrase in [
            "best",
            "favorite",
            "highest rated",
            "top",
            "where should",
            "recommend",
        ]
    )


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clip(value: Any, length: int) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if len(text) <= length:
        return text
    return f"{text[: length - 1].rstrip()}..."
