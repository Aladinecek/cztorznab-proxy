from lxml import etree

from app.main import _rewrite_and_filter

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


def test_season_filter_rewrites_and_drops_non_matching():
    result = _rewrite_and_filter(FIXTURE, season=6)
    assert _titles(result) == [
        "Grimm S06 (2016)(CZ)[1080p]",
        "Grimm S01-S06 COMPLETE (2011)(CZ)[1080p]",
    ]


def test_season_filter_keeps_seeders_attribute_on_surviving_items():
    result = _rewrite_and_filter(FIXTURE, season=6)
    root = etree.fromstring(result)
    seeders = [
        item.find("{http://torznab.com/schemas/2015/feed}attr").get("value")
        for item in root.iter("item")
    ]
    assert seeders == ["10", "5"]


def test_no_season_means_no_filtering_only_rewrite():
    result = _rewrite_and_filter(FIXTURE, season=None)
    assert _titles(result) == [
        "Grimm S06 (2016)(CZ)[1080p]",
        "Grimm S01-S06 COMPLETE (2011)(CZ)[1080p]",
        "Grimm S05 (2015)(CZ)[1080p]",
    ]
