import logging

import pytest
from lxml import etree

from app.main import _rewrite_and_filter

pytestmark = pytest.mark.anyio

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:torznab="http://torznab.com/schemas/2015/feed" version="2.0">
  <channel>
    <title>Sk-CzTorrent</title>
    <item>
      <title>Grimm 6. série (2016)(CZ)[1080p]</title>
      <torznab:attr name="seeders" value="10" />
    </item>
    <item>
      <title>Grimm 1-6. serie (2011-2016)(CZ)[1080p]</title>
      <torznab:attr name="seeders" value="5" />
    </item>
    <item>
      <title>Grimm 5. série (2015)(CZ)[1080p]</title>
      <torznab:attr name="seeders" value="8" />
    </item>
  </channel>
</rss>""".encode("utf-8")


def _titles(xml_bytes: bytes) -> list[str]:
    root = etree.fromstring(xml_bytes)
    return [item.find("title").text for item in root.iter("item")]


async def test_season_filter_rewrites_and_drops_non_matching():
    result = await _rewrite_and_filter(FIXTURE, season=6)
    assert _titles(result) == [
        "Grimm S06 (2016)(CZ)[1080p]",
        "Grimm S01-S06 COMPLETE (2011)(CZ)[1080p]",
    ]


async def test_season_filter_keeps_seeders_attribute_on_surviving_items():
    result = await _rewrite_and_filter(FIXTURE, season=6)
    root = etree.fromstring(result)
    seeders = [
        item.find("{http://torznab.com/schemas/2015/feed}attr").get("value")
        for item in root.iter("item")
    ]
    assert seeders == ["10", "5"]


async def test_no_season_means_no_filtering_only_rewrite():
    result = await _rewrite_and_filter(FIXTURE, season=None)
    assert _titles(result) == [
        "Grimm S06 (2016)(CZ)[1080p]",
        "Grimm S01-S06 COMPLETE (2011)(CZ)[1080p]",
        "Grimm S05 (2015)(CZ)[1080p]",
    ]


async def test_season_filter_logs_one_summary_line_per_request(caplog):
    with caplog.at_level(logging.INFO, logger="cztorznab_proxy"):
        await _rewrite_and_filter(FIXTURE, season=6)

    info_records = [r for r in caplog.records if r.levelname == "INFO"]
    assert len(info_records) == 1
    assert "kept 2/3 items" in info_records[0].message


async def test_no_season_logs_no_summary_line(caplog):
    with caplog.at_level(logging.INFO, logger="cztorznab_proxy"):
        await _rewrite_and_filter(FIXTURE, season=None)

    assert not [r for r in caplog.records if r.levelname == "INFO"]


async def test_unmatched_pattern_warns_without_blocking_other_items(caplog):
    fixture = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:torznab="http://torznab.com/schemas/2015/feed" version="2.0">
  <channel>
    <item><title>Grimm serie 6 (2016)(CZ)[1080p]</title></item>
    <item><title>Grimm 6. serie (2016)(CZ)[1080p]</title></item>
  </channel>
</rss>""".encode("utf-8")

    with caplog.at_level(logging.WARNING, logger="cztorznab_proxy"):
        result = await _rewrite_and_filter(fixture, season=None)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "unmatched CZ pattern" in warnings[0].message
    assert _titles(result) == [
        "Grimm serie 6 (2016)(CZ)[1080p]",
        "Grimm S06 (2016)(CZ)[1080p]",
    ]
