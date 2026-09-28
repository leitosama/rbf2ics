import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
# The function is deployed with rbf2ics/ as its root (entrypoint app.lambda_handler).
sys.path.insert(0, str(ROOT / "rbf2ics"))

import app  # noqa: E402

TEAM_ID = 2093  # home team (TeamAid) of the first game in sample.json
ARENA_ID = 11790  # its arena
ARENA_NAME = "Академия баскетбола «Зенит»"  # its ArenaRu
ARENAS_JSON = ROOT / "frontend" / "data" / "arenas.json"


def _ns(d):
    return SimpleNamespace(**d)


@pytest.fixture()
def apigw_event():
    """API Gateway event for GET /ics/{team_id}/{arena_ids}.ics"""
    return json.loads((ROOT / "events" / "event.json").read_text())


@pytest.fixture()
def arenas_file(tmp_path, monkeypatch):
    """Points the function at a temporary arenas.json and resets its cache"""
    path = tmp_path / "arenas.json"
    path.write_text(json.dumps({"arenas": [
        {"id": ARENA_ID, "name": "Test; arena", "address": "Street, 1", "city": "Test"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(app, "ARENAS_PATH", str(path))
    monkeypatch.setattr(app, "_arenas", None)
    return path


@pytest.fixture()
def rbf_api(monkeypatch, arenas_file):
    """Stubs the RBF API with sample.json and records the requested team ids"""
    games = json.loads((ROOT / "sample.json").read_text(), object_hook=_ns)
    for game in games:
        game.json = game
    team_info = _ns({"CurrentTeamName": _ns({"CompTeamShortNameRu": "Тест"})})
    team_info.json = team_info
    calls = []

    def get_team_info(team_id):
        calls.append(team_id)
        return team_info

    monkeypatch.setattr(app, "get_team_info", get_team_info)
    monkeypatch.setattr(app, "get_team_games", lambda team_id: games)
    return calls


def _event(apigw_event, team_id, arena_ids, keys=("params", "pathParameters")):
    event = copy.deepcopy(apigw_event)
    event.pop("params", None)
    event.pop("pathParameters", None)
    for key in keys:
        event[key] = {"team_id": str(team_id), "arena_ids": arena_ids}
    event["url"] = f"/ics/{team_id}/{arena_ids}.ics"
    return event


def test_handler_returns_calendar(apigw_event, rbf_api):
    ret = app.lambda_handler(apigw_event, None)

    assert ret["statusCode"] == 200
    assert ret["headers"]["Content-Type"].startswith("text/calendar")
    assert ret["body"].startswith("BEGIN:VCALENDAR")
    assert ret["body"].endswith("END:VCALENDAR")
    assert ret["body"].count("BEGIN:VEVENT") == 34
    assert rbf_api == [3204]


@pytest.mark.parametrize("keys", [("params",), ("pathParameters",)])
def test_handler_uses_path_parameters(apigw_event, rbf_api, keys):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID), keys), None)

    assert rbf_api == [TEAM_ID]
    assert f"{app.HOME_EMOJI} " in ret["body"]
    assert r"LOCATION:Test\; arena\nStreet\, 1" in ret["body"]


def test_handler_uses_first_of_multiple_arenas(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, f"{ARENA_ID}_11926"), None)

    assert r"LOCATION:Test\; arena\nStreet\, 1" in ret["body"]


def test_handler_other_arena_is_not_home(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, "11926"), None)

    assert f"{app.HOME_EMOJI} " not in ret["body"]


def test_handler_defaults_without_params(apigw_event, rbf_api):
    event = copy.deepcopy(apigw_event)
    del event["params"], event["pathParameters"]

    ret = app.lambda_handler(event, None)

    assert ret["statusCode"] == 200
    assert rbf_api == [app.HOME_TEAMID]


def test_handler_falls_back_to_arena_name_without_arenas_file(apigw_event, rbf_api, arenas_file):
    arenas_file.unlink()

    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID)), None)

    assert ret["statusCode"] == 200
    assert f"LOCATION:{ARENA_NAME}" in ret["body"]


def test_arenas_load_retries_after_failure(arenas_file):
    content = arenas_file.read_text(encoding="utf-8")
    arenas_file.unlink()
    assert app.get_arenas() == {}

    arenas_file.write_text(content, encoding="utf-8")
    assert list(app.get_arenas()) == [ARENA_ID]


def test_handler_falls_back_to_arena_name_for_unknown_arena(apigw_event, rbf_api, arenas_file):
    arenas_file.write_text(json.dumps({"arenas": []}), encoding="utf-8")

    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID)), None)

    assert f"LOCATION:{ARENA_NAME}" in ret["body"]


def test_ics_escape():
    assert app.ics_escape("a\\b;c,d\ne") == r"a\\b\;c\,d\ne"


def test_arenas_json_is_valid():
    arenas = json.loads(ARENAS_JSON.read_text(encoding="utf-8"))["arenas"]

    ids = [arena["id"] for arena in arenas]
    assert all(type(aid) is int for aid in ids)
    assert len(ids) == len(set(ids))
    for arena in arenas:
        for field in ("name", "address", "city"):
            assert isinstance(arena[field], str) and arena[field].strip(), (arena["id"], field)
