"""Phase 2 (not implemented): translate Czech movie/show titles to English via TMDB.

TMDB_API_KEY is read from the environment so the future implementation has a
single place to pick it up; it is unused until translate_title is implemented.
"""

import os

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")


def translate_title(cz_title: str) -> str | None:
    raise NotImplementedError
