# cztorznab-proxy

A transparent Torznab proxy that sits between [Prowlarr](https://prowlarr.com/)
and [Jackett](https://github.com/Jackett/Jackett), rewriting Czech/Slovak
torrent tracker release names into a format Sonarr/Radarr can actually parse.

## The problem

Czech and Slovak trackers (e.g. Sk-CzTorrent on Jackett) name TV releases
using local conventions instead of the scene-standard `SxxExx` format:

```
Dexter 1-8. serie (2006-2013)(CZ/EN)[1080p][HEVC]
Simpsonovi 35. serie 12. díl CZ dabing
Pařba ve Vegas (2009) UHDRDV cz en
```

Sonarr and Radarr's release parser doesn't understand `. serie`, `. díl`, or
`cz dabing`, and chokes on diacritics — so these releases get silently
rejected even though they're exactly what you searched for. Worse: Jackett's
own `tvsearch` season filter matches against the *raw* title, so a release
like `6. série` never matches `season=6` and gets dropped by Jackett before
your Sonarr/Radarr instance ever sees it — no amount of downstream parsing
fixes that, because the release is gone by the time it gets there.

## How it works

`cztorznab-proxy` sits in front of Jackett and transparently forwards every
request. It only touches two things:

**1. Title rewriting** — for Torznab XML responses, each `<title>` is rewritten
through a small regex pipeline (case-insensitive, applied in this order):

| # | Pattern | Rewrite |
|---|---------|---------|
| 1 | `X-Y. serie` / `X-Y. série` | `SXX-SYY COMPLETE` (season range, run first) |
| 2 | `X. serie` / `X. série` | `SXX` |
| 3 | `X. díl` / `X. epizoda` / `X. ep` | `EXX` |
| 4 | Year range in parens `(2006-2013)` | first year only `(2006)` |
| 5 | `dabing`, `cz dabing`, `czdab`, `cesky`/`český`, bare `cz` | `CZ` |
| 6 | Diacritics | transliterated to ASCII |
| 7 | Repeated whitespace | collapsed to a single space |

Everything else in the response — torznab attributes, enclosure URLs, sizes,
seeders, `.torrent` downloads, `t=caps` — passes through byte-for-byte
unmodified. If a response can't be parsed as XML, it's returned as-is.

**2. Season-aware `tvsearch` filtering** — because Jackett filters
`tvsearch&season=N` requests against the raw, un-rewritten title, a season
pack like `1-8. série` never matches and is dropped upstream before rewriting
can help. The proxy works around this: for `tvsearch` requests carrying a
`season` parameter, it strips `season`/`ep` before forwarding to Jackett (so
Jackett returns the full, unfiltered result set for the query), rewrites every
title, and *then* filters locally — keeping items whose rewritten title
contains the matching season (`S06`), a range that covers it (`S01-S08`), or
`COMPLETE`. `limit`/`offset` are still forwarded upstream as normal. Requests
without a `season` parameter (plain `t=search`, or `tvsearch` without a
season) pass through unfiltered, as before.

### Before / after

| Raw Jackett title | Rewritten by proxy |
|---|---|
| `Dexter 1-8. serie (2006-2013)(CZ/EN)[1080p][HEVC]` | `Dexter S01-S08 COMPLETE (2006)(CZ/EN)[1080p][HEVC]` |
| `Simpsonovi 35. serie 12. díl CZ dabing` | `Simpsonovi S35 E12 CZ` |
| `Pařba ve Vegas (2009) UHDRDV cz en` | `Parba ve Vegas (2009) UHDRDV CZ en` |
| `The Simpsons 36. série (2024)(CZ)[1080p][TvRip]` | `The Simpsons S36 (2024)(CZ)[1080p][TvRip]` |

## Installation

No cloning, no building — just a `docker-compose.yml` and one command, the
same way you'd stand up Jellyfin. Requires an existing Jackett instance
reachable from Docker (e.g. as part of your media stack's compose setup).

1. Make a folder for it and grab the compose file:

   ```bash
   mkdir cztorznab-proxy && cd cztorznab-proxy
   curl -O https://raw.githubusercontent.com/Aladinecek/cztorznab-proxy/main/docker-compose.yml
   ```

2. Open `docker-compose.yml` and edit the two marked lines: `JACKETT_URL`
   (Jackett's address) and the `networks:` block (the Docker network your
   Jackett container is on, so the proxy can reach it by container name —
   check with `docker inspect <jackett-container>` if unsure).
3. Start it:

   ```bash
   docker compose up -d
   ```

   That's it — `docker compose pull` grabs the prebuilt image from
   `ghcr.io/aladinecek/cztorznab-proxy` (published for `linux/amd64` and
   `linux/arm64`, Raspberry Pi included) automatically on `up`. Nothing to
   build.

4. In Prowlarr, change the indexer's Torznab URL from Jackett directly to the
   proxy, keeping the same path and API key:

   ```
   before: http://jackett:9117/api/v2.0/indexers/<indexer>/results/torznab/
   after:  http://cztorznab-proxy:8000/api/v2.0/indexers/<indexer>/results/torznab/
   ```

   The indexer's API key is never stored by the proxy — it's forwarded
   straight through from Prowlarr to Jackett on every request.

5. Run a test search in Prowlarr and confirm titles now show up in
   `SxxExx`/`CZ`/ASCII form.

Building from source instead of pulling? See [Development](#development).

## Updating

Pull the latest image and recreate the container:

```bash
docker compose pull
docker compose up -d
```

If you'd rather not do this by hand, point
[Watchtower](https://containrrr.dev/watchtower/) at the `cztorznab-proxy`
container (e.g. via its `com.centurylinklabs.watchtower.enable=true` label)
and it'll pick up new `:latest` images automatically.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `JACKETT_URL` | `http://localhost:9117` | Base URL of the upstream Jackett instance |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` to log every title rewrite as `title rewrite: 'original' -> 'new'` |
| `TMDB_API_KEY` | _(unused)_ | Reserved for phase 2, see below — not yet implemented |

No API key is configured on the proxy itself; Torznab API keys are query
parameters that pass through from Prowlarr to Jackett unchanged.

## Development

```bash
git clone https://github.com/Aladinecek/cztorznab-proxy.git
cd cztorznab-proxy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Run locally against an existing Jackett instance without Docker:

```bash
JACKETT_URL=http://localhost:9117 LOG_LEVEL=DEBUG \
    uvicorn app.main:app --reload --port 8000
```

## Phase 2 (interface only, not implemented)

`app/tmdb.py` defines the interface for a future feature: translating Czech
movie/show titles to English via the TMDB API (`translate_title(cz_title) ->
str | None`). It currently raises `NotImplementedError`. `TMDB_API_KEY` is
read from the environment but unused until this ships.

## License

MIT — see [LICENSE](LICENSE).
