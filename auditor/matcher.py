"""Matching utilities for source-vs-published story comparison."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


def normalize_title(title: str) -> str:
    """Normalize story titles for deterministic comparison."""
    if not title:
        return ""
    normalized = title.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^[\"'“”‘’]+|[\"'“”‘’]+$", "", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def canonicalize_url(url: str) -> str:
    """Normalize URL by stripping fragments and common tracking query params."""
    if not url:
        return ""
    candidate = url.strip()
    if not candidate:
        return ""
    if not (candidate.startswith("http://") or candidate.startswith("https://")):
        return ""

    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = (parsed.path or "").rstrip("/")
    path = path or "/"

    filtered_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_l = key.lower()
        if key_l.startswith("utm_"):
            continue
        if key_l in TRACKING_QUERY_KEYS:
            continue
        filtered_query.append((key, value))
    filtered_query.sort(key=lambda item: item[0].lower())
    query = urlencode(filtered_query, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def _best_fuzzy_title_match(source_title: str, candidates: list[dict], threshold: float) -> tuple[dict | None, float]:
    """Return best fuzzy title candidate and score, or (None, 0)."""
    source_norm = normalize_title(source_title)
    if not source_norm:
        return None, 0.0

    best_item = None
    best_score = 0.0
    for candidate in candidates:
        score = SequenceMatcher(None, source_norm, normalize_title(candidate.get("title", ""))).ratio()
        if score > best_score:
            best_score = score
            best_item = candidate
    if best_item is None or best_score < threshold:
        return None, best_score
    return best_item, best_score


def find_best_match(source_item: dict, published_items: list[dict], fuzzy_threshold: float = 0.92) -> dict | None:
    """Find best published match for a source item.

    Returns:
        {
          "matched_item": {...},
          "match_type": "url_exact" | "title_exact" | "title_fuzzy",
          "score": float,
          "cross_source": bool,
        }
        or None if no match found.
    """
    source_tab = source_item.get("tab", "")
    source_id = source_item.get("source_id", "")
    source_url = canonicalize_url(source_item.get("url", ""))
    source_title_norm = normalize_title(source_item.get("title", ""))

    same_tab = [item for item in published_items if item.get("tab") == source_tab]
    if not same_tab:
        return None

    same_source = [item for item in same_tab if item.get("source_id", "") == source_id]
    scopes = [("same_source", same_source), ("same_tab", same_tab)]

    for scope_name, candidates in scopes:
        if not candidates:
            continue

        if source_url:
            for candidate in candidates:
                if canonicalize_url(candidate.get("url", "")) == source_url:
                    return {
                        "matched_item": candidate,
                        "match_type": "url_exact",
                        "score": 1.0,
                        "cross_source": scope_name != "same_source",
                    }

        if source_title_norm:
            for candidate in candidates:
                if normalize_title(candidate.get("title", "")) == source_title_norm:
                    return {
                        "matched_item": candidate,
                        "match_type": "title_exact",
                        "score": 1.0,
                        "cross_source": scope_name != "same_source",
                    }

            fuzzy_item, fuzzy_score = _best_fuzzy_title_match(source_item.get("title", ""), candidates, fuzzy_threshold)
            if fuzzy_item:
                return {
                    "matched_item": fuzzy_item,
                    "match_type": "title_fuzzy",
                    "score": round(fuzzy_score, 4),
                    "cross_source": scope_name != "same_source",
                }

    return None

