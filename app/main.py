import logging
import os

import httpx
from fastapi import FastAPI, Request, Response
from lxml import etree

from .transform import has_unrewritten_marker, matches_season, transform_title

JACKETT_URL = os.environ.get("JACKETT_URL", "http://localhost:9117").rstrip("/")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("cztorznab_proxy")

app = FastAPI(title="cztorznab-proxy")

_client = httpx.AsyncClient(timeout=30.0)

# Headers that are per-hop and must not be blindly copied between proxy legs.
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
    "host",
}


def _looks_like_torznab_xml(content_type: str, body: bytes) -> bool:
    content_type = content_type.lower()
    if "xml" not in content_type and "rss" not in content_type:
        return False
    return b"<item" in body


def _extract_season(query_params) -> int | None:
    """Jackett filters tvsearch results on the raw (un-rewritten) title, so a
    release like "6. série" never matches season=6 and gets dropped before we
    ever see it. Stripping season/ep from the upstream request and filtering
    on the rewritten title ourselves (see _rewrite_and_filter) works around
    that.
    """
    if query_params.get("t") != "tvsearch":
        return None
    season_raw = query_params.get("season")
    if not season_raw:
        return None
    try:
        return int(season_raw)
    except ValueError:
        return None


def _build_upstream_params(query_params, season: int | None) -> list[tuple[str, str]]:
    params = list(query_params.multi_items())
    if season is not None:
        # limit/offset stay in the upstream request - only season/ep are
        # dropped, since filtering happens locally after the rewrite.
        params = [(k, v) for k, v in params if k not in ("season", "ep")]
    return params


def _rewrite_and_filter(body: bytes, season: int | None) -> bytes:
    parser = etree.XMLParser(recover=True, strip_cdata=False)
    root = etree.fromstring(body, parser=parser)
    total = 0
    dropped = 0
    for item in list(root.iter("item")):
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            continue
        total += 1
        original = title_el.text
        new = transform_title(original)
        if new != original:
            if LOG_LEVEL == "DEBUG":
                logger.debug("title rewrite: %r -> %r", original, new)
            title_el.text = new
        if has_unrewritten_marker(title_el.text):
            # Rare by design (most titles either need no rewrite at all, or get
            # fully rewritten) - safe to always log, even under heavy Sonarr/
            # Radarr/Bazarr search traffic.
            logger.warning("unmatched CZ pattern survived rewrite: %r", title_el.text)
        if season is not None and not matches_season(title_el.text, season):
            dropped += 1
            if LOG_LEVEL == "DEBUG":
                logger.debug("season filter: dropped (season=%d) %r", season, title_el.text)
            parent = item.getparent()
            if parent is not None:
                parent.remove(item)
    if season is not None and total:
        # One line per request, not per item - stays cheap even with the
        # request volume Sonarr/Radarr/Bazarr generate.
        logger.info("season filter (season=%d): kept %d/%d items", season, total - dropped, total)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


@app.api_route("/{path:path}", methods=["GET", "POST", "HEAD"])
async def proxy(path: str, request: Request):
    url = f"{JACKETT_URL}/{path}"
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS
    }
    body = await request.body()

    season = _extract_season(request.query_params)
    params = _build_upstream_params(request.query_params, season)

    upstream = await _client.request(
        request.method,
        url,
        params=params,
        headers=headers,
        content=body,
    )

    content_type = upstream.headers.get("content-type", "")
    response_body = upstream.content

    if _looks_like_torznab_xml(content_type, response_body):
        try:
            response_body = _rewrite_and_filter(response_body, season)
        except etree.XMLSyntaxError:
            logger.warning("failed to parse XML from %s, passing through unmodified", url)

    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS
    }

    return Response(
        content=response_body,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=content_type or None,
    )
