from starlette.datastructures import QueryParams

from app.main import _build_upstream_params, _extract_season


def test_extract_season_from_tvsearch():
    qp = QueryParams("t=tvsearch&q=grimm&season=6&ep=3&apikey=x")
    assert _extract_season(qp) == 6


def test_extract_season_none_for_plain_search():
    qp = QueryParams("t=search&q=grimm&apikey=x")
    assert _extract_season(qp) is None


def test_extract_season_none_when_season_missing():
    qp = QueryParams("t=tvsearch&q=grimm&apikey=x")
    assert _extract_season(qp) is None


def test_build_upstream_params_strips_season_and_ep_keeps_limit_offset():
    qp = QueryParams("t=tvsearch&q=grimm&season=6&ep=3&limit=50&offset=0&apikey=x")
    params = _build_upstream_params(qp, season=6)
    keys = [k for k, _ in params]
    assert "season" not in keys
    assert "ep" not in keys
    assert ("limit", "50") in params
    assert ("offset", "0") in params
    assert ("q", "grimm") in params


def test_build_upstream_params_passthrough_when_no_season_filtering():
    qp = QueryParams("t=search&q=grimm&apikey=x")
    params = _build_upstream_params(qp, season=None)
    assert params == list(qp.multi_items())
