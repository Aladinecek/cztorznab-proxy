from unittest.mock import AsyncMock, MagicMock

import pytest

from app import tmdb

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def isolate_tmdb_state(tmp_path, monkeypatch):
    # Every test gets a clean in-memory cache backed by a throwaway file, so
    # no test can see another test's cached translation or touch real disk.
    monkeypatch.setattr(tmdb, "_cache", {})
    monkeypatch.setattr(tmdb, "_cache_loaded", False)
    monkeypatch.setattr(tmdb, "_CACHE_PATH", tmp_path / "tmdb_titles.json")
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "test-key")


def _mock_response(json_data):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


async def test_maybe_translate_noop_without_api_key(monkeypatch):
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", None)
    mock_get = AsyncMock()
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    result = await tmdb.maybe_translate("Cerveny trpaslik BDrip S01-S13 CZ H.265 1080p (1988)")

    assert result == "Cerveny trpaslik BDrip S01-S13 CZ H.265 1080p (1988)"
    mock_get.assert_not_called()


async def test_maybe_translate_still_queries_tmdb_without_diacritics(monkeypatch):
    # Regression test: some trackers already write names without diacritics
    # even when untranslated (e.g. "Cerveny trpaslik" for Red Dwarf, no
    # accents at all) - gating on "has diacritics" would silently skip these,
    # which is exactly what happened before this was fixed. TMDB must still
    # be queried; a low-similarity/no-match result is what actually leaves
    # a harmless title like "Grimm" untouched, not a diacritics precheck.
    mock_get = AsyncMock(return_value=_mock_response({"results": []}))
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    result = await tmdb.maybe_translate("Grimm 6. serie (2016)(CZ)[1080p]")

    assert result == "Grimm 6. serie (2016)(CZ)[1080p]"
    mock_get.assert_awaited_once()


async def test_maybe_translate_handles_bilingual_prefix_without_diacritics(monkeypatch):
    # The exact real-world case that motivated the fix above: raw Jackett
    # title has no diacritics at all ("Cerveny trpaslik", not "Cervený
    # trpaslík"), only the TMDB Czech localization does.
    search_response = _mock_response(
        {
            "results": [
                {
                    "media_type": "tv",
                    "id": 42,
                    "name": "Červený trpaslík",
                    "original_name": "Red Dwarf",
                    "original_language": "en",
                }
            ]
        }
    )
    mock_get = AsyncMock(return_value=search_response)
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    result = await tmdb.maybe_translate("Red Dwarf - Cerveny trpaslik BDrip S01-S13 CZ H.265 1080p (1988)")

    assert result == "Red Dwarf BDrip S01-S13 CZ H.265 1080p (1988)"


async def test_maybe_translate_replaces_confident_match(monkeypatch):
    search_response = _mock_response(
        {
            "results": [
                {
                    "media_type": "tv",
                    "id": 42,
                    "name": "Červený trpaslík",
                    "original_name": "Red Dwarf",
                    "original_language": "en",
                }
            ]
        }
    )
    mock_get = AsyncMock(return_value=search_response)
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    result = await tmdb.maybe_translate("Červený trpaslík BDrip S01-S13 CZ H.265 1080p (1988)")

    assert result == "Red Dwarf BDrip S01-S13 CZ H.265 1080p (1988)"
    mock_get.assert_awaited_once()


async def test_maybe_translate_handles_bilingual_prefix(monkeypatch):
    # "Red Dwarf - Cerveny trpaslik" style titles: TMDB only has the Czech
    # part as its localized name, but the whole candidate (with the English
    # prefix) is what gets matched against and replaced.
    search_response = _mock_response(
        {
            "results": [
                {
                    "media_type": "tv",
                    "id": 42,
                    "name": "Červený trpaslík",
                    "original_name": "Red Dwarf",
                    "original_language": "en",
                }
            ]
        }
    )
    mock_get = AsyncMock(return_value=search_response)
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    result = await tmdb.maybe_translate("Red Dwarf - Červený trpaslík BDrip S01-S13 CZ H.265 1080p (1988)")

    assert result == "Red Dwarf BDrip S01-S13 CZ H.265 1080p (1988)"


async def test_maybe_translate_leaves_unchanged_on_low_similarity(monkeypatch):
    search_response = _mock_response(
        {
            "results": [
                {
                    "media_type": "tv",
                    "id": 99,
                    "name": "Naprosto nesouvisející název",
                    "original_name": "Completely Unrelated",
                    "original_language": "en",
                }
            ]
        }
    )
    mock_get = AsyncMock(return_value=search_response)
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    original = "Červený trpaslík BDrip S01-S13 CZ H.265 1080p (1988)"
    result = await tmdb.maybe_translate(original)

    assert result == original


async def test_maybe_translate_leaves_unchanged_on_no_results(monkeypatch):
    mock_get = AsyncMock(return_value=_mock_response({"results": []}))
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    original = "Červený trpaslík BDrip S01-S13 CZ H.265 1080p (1988)"
    result = await tmdb.maybe_translate(original)

    assert result == original


async def test_maybe_translate_leaves_unchanged_on_tmdb_error(monkeypatch):
    import httpx

    mock_get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    original = "Červený trpaslík BDrip S01-S13 CZ H.265 1080p (1988)"
    result = await tmdb.maybe_translate(original)

    assert result == original


async def test_maybe_translate_uses_cache_on_second_call(monkeypatch):
    search_response = _mock_response(
        {
            "results": [
                {
                    "media_type": "tv",
                    "id": 42,
                    "name": "Červený trpaslík",
                    "original_name": "Red Dwarf",
                    "original_language": "en",
                }
            ]
        }
    )
    mock_get = AsyncMock(return_value=search_response)
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    title = "Červený trpaslík BDrip S01-S13 CZ H.265 1080p (1988)"
    first = await tmdb.maybe_translate(title)
    second = await tmdb.maybe_translate(title)

    assert first == second == "Red Dwarf BDrip S01-S13 CZ H.265 1080p (1988)"
    mock_get.assert_awaited_once()


async def test_maybe_translate_falls_back_to_detail_lookup_for_non_english_original(monkeypatch):
    search_response = _mock_response(
        {
            "results": [
                {
                    "media_type": "tv",
                    "id": 7,
                    "name": "Papírový dům",
                    "original_name": "La Casa de Papel",
                    "original_language": "es",
                }
            ]
        }
    )
    detail_response = _mock_response({"name": "Money Heist"})
    mock_get = AsyncMock(side_effect=[search_response, detail_response])
    monkeypatch.setattr(tmdb._client, "get", mock_get)

    result = await tmdb.maybe_translate("Papírový dům BDrip CZ H.265 1080p (2017)")

    assert result == "Money Heist BDrip CZ H.265 1080p (2017)"
    assert mock_get.await_count == 2


def test_extract_name_candidate_none_when_no_boundary_marker():
    assert tmdb._extract_name_candidate("Just Some Words") is None
