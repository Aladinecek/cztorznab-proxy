import re

from unidecode import unidecode

# s[ée]rie matches both the ASCII "serie" and the correctly accented "série"
# Jackett actually returns.
# Rule 2 must run before rule 1: "1-8. serie" would otherwise be partially
# consumed by the single-serie pattern before the range pattern gets a chance.
_RANGE_SERIE_RE = re.compile(r"(\d+)\s*-\s*(\d+)\.\s*s[ée]rie", re.IGNORECASE)
_SINGLE_SERIE_RE = re.compile(r"(\d+)\.\s*s[ée]rie", re.IGNORECASE)
_EPISODE_RE = re.compile(r"(\d+)\.\s*(epizoda|d[ií]l|ep)\b", re.IGNORECASE)
_YEAR_RANGE_RE = re.compile(r"\((\d{4})-\d{4}\)")
_CZ_TOKEN_RE = re.compile(
    r"\b(cz\s*dabing|czdab|dabing|česk[yý]|cesky|cz)\b", re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"\s+")

# Matched against a title *after* transform_title() has run, so "série" is
# already normalized to "S06"/"S01-S08 COMPLETE" etc. The lookaround (instead
# of \b) is needed because season and episode sit back-to-back with no
# separator in pre-formatted uploader titles like "S06E12".
_SEASON_RANGE_RE = re.compile(r"(?<!\w)S(\d{2})-S(\d{2})(?!\d)")
_SEASON_SINGLE_RE = re.compile(r"(?<!\w)S(\d{2})(?!\d)")


def _replace_range_serie(match: "re.Match[str]") -> str:
    start, end = int(match.group(1)), int(match.group(2))
    return f"S{start:02d}-S{end:02d} COMPLETE"


def _replace_single_serie(match: "re.Match[str]") -> str:
    return f"S{int(match.group(1)):02d}"


def _replace_episode(match: "re.Match[str]") -> str:
    return f"E{int(match.group(1)):02d}"


def transform_title(title: str) -> str:
    title = _RANGE_SERIE_RE.sub(_replace_range_serie, title)
    title = _SINGLE_SERIE_RE.sub(_replace_single_serie, title)
    title = _EPISODE_RE.sub(_replace_episode, title)
    title = _YEAR_RANGE_RE.sub(r"(\1)", title)
    title = _CZ_TOKEN_RE.sub("CZ", title)
    title = unidecode(title)
    title = _WHITESPACE_RE.sub(" ", title).strip()
    return title


def matches_season(title: str, season: int) -> bool:
    if "COMPLETE" in title:
        return True
    for start, end in _SEASON_RANGE_RE.findall(title):
        if int(start) <= season <= int(end):
            return True
    for s in _SEASON_SINGLE_RE.findall(title):
        if int(s) == season:
            return True
    return False
