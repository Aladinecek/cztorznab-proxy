from app.transform import has_unrewritten_marker, matches_season, transform_title


def test_range_serie_complete():
    assert (
        transform_title("Dexter 1-8. serie (2006-2013)(CZ/EN)[1080p][HEVC]")
        == "Dexter S01-S08 COMPLETE (2006)(CZ/EN)[1080p][HEVC]"
    )


def test_diacritics_and_cz_token():
    assert (
        transform_title("Pařba ve Vegas (2009) UHDRDV cz en")
        == "Parba ve Vegas (2009) UHDRDV CZ en"
    )


def test_serie_episode_and_dabing_collapse():
    assert (
        transform_title("Simpsonovi 35. serie 12. díl CZ dabing")
        == "Simpsonovi S35 E12 CZ"
    )


def test_single_serie():
    assert transform_title("3. serie") == "S03"


def test_single_serie_with_diacritics():
    # Real Jackett output uses the correctly accented "série", not "serie".
    assert (
        transform_title("The Simpsons 36. série (2024)(CZ)[1080p][TvRip]")
        == "The Simpsons S36 (2024)(CZ)[1080p][TvRip]"
    )


def test_range_serie_with_diacritics():
    assert transform_title("Dexter 1-8. série (2006-2013)") == "Dexter S01-S08 COMPLETE (2006)"


def test_episode_variants():
    assert transform_title("5. epizoda") == "E05"
    assert transform_title("5. ep") == "E05"


def test_year_range_keeps_first_year_only():
    assert transform_title("(2006-2013)") == "(2006)"


def test_year_without_range_untouched():
    assert transform_title("(2009)") == "(2009)"


def test_cz_dabing_tokens_normalize():
    assert transform_title("czdab") == "CZ"
    assert transform_title("dabing") == "CZ"
    assert transform_title("cesky") == "CZ"
    assert transform_title("cz dabing") == "CZ"


def test_multiple_spaces_collapsed():
    assert transform_title("Foo   Bar    Baz") == "Foo Bar Baz"


def test_matches_season_single():
    assert matches_season("Grimm S06 (2016)(CZ)[1080p]", 6)
    assert not matches_season("Grimm S05 (2015)(CZ)[1080p]", 6)


def test_matches_season_embedded_before_episode():
    # Pre-formatted uploader titles like "S06E12" have no separator between
    # season and episode.
    assert matches_season("Grimm S06E12 (2016)(CZ)[1080p]", 6)


def test_matches_season_range_covers_season():
    assert matches_season("Grimm S01-S06 COMPLETE (2011)(CZ)[1080p]", 6)
    # No COMPLETE token here on purpose - isolates the range-boundary check
    # from the "COMPLETE always matches" rule.
    assert not matches_season("Grimm S01-S05 (2011)(CZ)[1080p]", 6)


def test_matches_season_complete_matches_any_season():
    assert matches_season("Grimm COMPLETE", 1)
    assert matches_season("Grimm COMPLETE", 99)


def test_has_unrewritten_marker_true_for_missed_pattern():
    # "serie" with no leading "N." doesn't match any rewrite rule, so it
    # survives transform_title() untouched - a real pattern gap.
    title = transform_title("Grimm serie 6 (2016)(CZ)[1080p]")
    assert has_unrewritten_marker(title)


def test_has_unrewritten_marker_false_after_successful_rewrite():
    title = transform_title("Simpsonovi 35. serie 12. díl CZ dabing")
    assert not has_unrewritten_marker(title)


def test_has_unrewritten_marker_false_for_plain_english_title():
    assert not has_unrewritten_marker("Dexter S01E02 (2006)(EN)[1080p]")


def test_quality_tag_before_season_gets_moved_after():
    # Sonarr's own parser confirmed (via /api/v3/parse) that a quality tag
    # sitting between the name and the season range gets swallowed into the
    # series title ("Red Dwarf BDrip"), which then fails to match TVDb.
    assert (
        transform_title("Red Dwarf BDrip S01-S13 CZ H.265 1080p (1988)")
        == "Red Dwarf S01-S13 BDrip CZ H.265 1080p (1988)"
    )


def test_quality_tag_before_season_with_complete_suffix():
    # The quality tag ends up right before the range-serie pattern once that
    # gets converted to "SXX-SYY COMPLETE" - COMPLETE must move along with
    # the season range, not get left stranded before the swapped-in quality.
    assert (
        transform_title("Grimm BDrip 1-6. serie (2011-2016)")
        == "Grimm S01-S06 COMPLETE BDrip (2011)"
    )


def test_quality_tags_already_after_season_untouched():
    assert transform_title("Dexter S01E02 1080p H.265 (2006)") == "Dexter S01E02 1080p H.265 (2006)"
