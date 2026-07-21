"""Phase 2: translate Czech movie/show titles to English via TMDB.

Attempted whenever TMDB_API_KEY is set and a name portion can be isolated
from the title - deliberately not gated on the title "looking Czech" (e.g.
containing diacritics): some trackers already strip accents from otherwise
untranslated names (e.g. "Cerveny trpaslik" for Red Dwarf, no diacritics at
all), so that signal misses real cases. The similarity-confidence gate is
what actually keeps this safe: an already-English title just matches itself
on TMDB and gets "replaced" with an identical string - a no-op. Any
uncertain case (no match, low similarity, TMDB unreachable) leaves the
title unchanged; this module never guesses.
"""

import asyncio
import json
import logging
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import httpx

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_CACHE_PATH = Path(os.environ.get("TMDB_CACHE_PATH", "/app/cache/tmdb_titles.json"))
_SIMILARITY_THRESHOLD = 0.72

logger = logging.getLogger("cztorznab_proxy.tmdb")

_client = httpx.AsyncClient(base_url="https://api.themoviedb.org/3", timeout=10.0)
_cache: dict[str, str | None] = {}
_cache_loaded = False
_cache_lock = asyncio.Lock()

# Boundary markers that end the "name" portion of a release title: a year,
# a Czech season/episode marker (pre-rewrite), an already-English SxxExx
# marker, or a common quality/format tag - whichever comes first wins.
_YEAR_RE = re.compile(r"\(\d{4}(?:-\d{4})?\)")
_SEASON_MARKER_RE = re.compile(
    r"(?:\d+\s*-\s*\d+\.\s*s[ée]rie|\d+\.\s*s[ée]rie|\d+\.\s*(?:epizoda|d[ií]l|ep)\b|"
    r"(?<!\w)S\d{2}(?:-S\d{2})?(?:E\d{2})?(?!\d))",
    re.IGNORECASE,
)
_QUALITY_TAG_RE = re.compile(
    r"\b(?:BDrip|BRRip|WEB-?DL|WEBRip|HDTV|DVDRip|REMUX|BluRay|HDR10?|"
    r"H\.?26[45]|x26[45]|\d{3,4}p)\b",
    re.IGNORECASE,
)


def _extract_name_candidate(title: str) -> str | None:
    positions = [
        m.start()
        for m in (_YEAR_RE.search(title), _SEASON_MARKER_RE.search(title), _QUALITY_TAG_RE.search(title))
        if m
    ]
    if not positions:
        return None
    candidate = title[: min(positions)].strip(" -:/–—")
    return candidate or None


def _similarity(name_candidate: str, local_name: str) -> float:
    # Bilingual releases like "Red Dwarf - Cerveny trpaslik" put the English
    # name TMDB won't have a Czech match for right next to the Czech one -
    # comparing only the whole candidate would drag the ratio down, so also
    # try just the tail segment after a common separator.
    variants = [name_candidate]
    for sep in (" - ", " / ", ": "):
        if sep in name_candidate:
            variants.append(name_candidate.rsplit(sep, 1)[-1].strip())
    return max(SequenceMatcher(None, v.lower(), local_name.lower()).ratio() for v in variants)


async def _load_cache() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    async with _cache_lock:
        if _cache_loaded:
            return
        if _CACHE_PATH.exists():
            try:
                _cache.update(json.loads(_CACHE_PATH.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                logger.debug("tmdb cache unreadable, starting fresh: %s", _CACHE_PATH)
        _cache_loaded = True


async def _save_cache() -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.debug("failed to persist tmdb cache to %s", _CACHE_PATH)


async def _tmdb_search(name_candidate: str) -> dict | None:
    try:
        resp = await _client.get(
            "/search/multi",
            params={"api_key": TMDB_API_KEY, "query": name_candidate, "language": "cs-CZ"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("TMDB search failed for %r: %s", name_candidate, exc)
        return None

    results = [r for r in resp.json().get("results", []) if r.get("media_type") in ("movie", "tv")]
    if not results:
        return None

    top = results[0]
    local_name = top.get("title") or top.get("name") or ""
    if _similarity(name_candidate, local_name) < _SIMILARITY_THRESHOLD:
        return None
    return top


async def _english_title(result: dict) -> str | None:
    if result.get("original_language") == "en":
        return result.get("original_title") or result.get("original_name")

    media_type = result["media_type"]
    tmdb_id = result["id"]
    try:
        resp = await _client.get(f"/{media_type}/{tmdb_id}", params={"api_key": TMDB_API_KEY, "language": "en-US"})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("TMDB detail lookup failed for id=%s: %s", tmdb_id, exc)
        return None
    data = resp.json()
    return data.get("title") or data.get("name")


async def _resolve_english_name(name_candidate: str) -> str | None:
    if not TMDB_API_KEY:
        return None

    await _load_cache()
    cache_key = name_candidate.lower()
    if cache_key in _cache:
        return _cache[cache_key]

    result = await _tmdb_search(name_candidate)
    english_name = await _english_title(result) if result else None

    async with _cache_lock:
        _cache[cache_key] = english_name
    await _save_cache()

    if english_name and LOG_LEVEL == "DEBUG":
        logger.debug("TMDB translate: %r -> %r", name_candidate, english_name)
    return english_name


async def maybe_translate(original_title: str) -> str:
    """Replace the Czech name portion of a release title with its English
    equivalent from TMDB, if a confident match is found. Returns the title
    unchanged in every uncertain case (disabled, no name portion to isolate,
    no match, low similarity, TMDB unreachable).
    """
    name_candidate = _extract_name_candidate(original_title)
    if not name_candidate:
        return original_title
    english_name = await _resolve_english_name(name_candidate)
    if not english_name:
        return original_title
    return original_title.replace(name_candidate, english_name, 1)
