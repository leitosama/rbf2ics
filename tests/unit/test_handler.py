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


def _ns(d):
    return SimpleNamespace(**d)


@pytest.fixture()
def apigw_event():
    """API Gateway event for GET /ics/{team_id}/{arena_ids}.ics"""
    return json.loads((ROOT / "events" / "event.json").read_text())


@pytest.fixture()
def rbf_api(monkeypatch):
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
    monkeypatch.setitem(app.ARENAS, ARENA_ID, {"address": "Test arena address"})
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
    assert "LOCATION:Test arena address" in ret["body"]


def test_handler_uses_first_of_multiple_arenas(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, f"{ARENA_ID}_11926"), None)

    assert "LOCATION:Test arena address" in ret["body"]


def test_handler_other_arena_is_not_home(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, "11926"), None)

    assert f"{app.HOME_EMOJI} " not in ret["body"]


def test_handler_defaults_without_params(apigw_event, rbf_api):
    event = copy.deepcopy(apigw_event)
    del event["params"], event["pathParameters"]

    ret = app.lambda_handler(event, None)

    assert ret["statusCode"] == 200
    assert rbf_api == [app.HOME_TEAMID]
