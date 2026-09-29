import copy
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# The function is deployed with rbf2ics/ as its root (entrypoint app.lambda_handler).
sys.path.insert(0, str(ROOT / "rbf2ics"))

import app  # noqa: E402

# sample.json is /api/abc/comps/calendar of БК Новосибирск (3204), season 2027
TEAM_ID = 3204
ARENA_ID = 11926  # arena of a single game in sample.json: ЦСКА-2 - Новосибирск
ARENAS_JSON = ROOT / "frontend" / "data" / "arenas.json"


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
def games():
    return json.loads((ROOT / "sample.json").read_text(encoding="utf-8"))["items"]


@pytest.fixture()
def rbf_api(monkeypatch, arenas_file, games):
    """Stubs the RBF API with sample.json and records the requested (team id, season)"""
    calls = []

    def get_team_games(team_id, season):
        calls.append((team_id, season))
        return games

    monkeypatch.setattr(app, "get_team_games", get_team_games)
    return calls


def _event(apigw_event, team_id, arena_ids, keys=("params", "pathParameters")):
    event = copy.deepcopy(apigw_event)
    event.pop("params", None)
    event.pop("pathParameters", None)
    for key in keys:
        event[key] = {"team_id": str(team_id), "arena_ids": arena_ids}
    event["url"] = f"/ics/{team_id}/{arena_ids}.ics"
    return event


def _events(body):
    return body.split("BEGIN:VEVENT\n")[1:]


def _event_of(body, game_id):
    return next(e for e in _events(body) if f"UID:{game_id}@rbf2ics\n" in e)


def test_handler_returns_calendar(apigw_event, rbf_api):
    ret = app.lambda_handler(apigw_event, None)

    assert ret["statusCode"] == 200
    assert ret["headers"]["Content-Type"].startswith("text/calendar")
    assert ret["body"].startswith("BEGIN:VCALENDAR")
    assert ret["body"].endswith("END:VCALENDAR")
    assert ret["body"].count("BEGIN:VEVENT") == 26
    assert "X-WR-CALNAME:БК Новосибирск\n" in ret["body"]
    assert rbf_api == [(3204, app.get_season())]


@pytest.mark.parametrize("keys", [("params",), ("pathParameters",)])
def test_handler_uses_path_parameters(apigw_event, rbf_api, keys):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID), keys), None)

    assert rbf_api == [(TEAM_ID, app.get_season())]
    assert ret["body"].count(f"{app.HOME_EMOJI} ") == 1
    assert r"LOCATION:Test\; arena\nStreet\, 1" in _event_of(ret["body"], 1083577)


def test_handler_all_arenas_are_home(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, f"11745_{ARENA_ID}"), None)

    # 13 games in СКК Север and 1 in ARENA_ID
    assert ret["body"].count(f"{app.HOME_EMOJI} ") == 14


def test_handler_other_arena_is_not_home(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, "1"), None)

    assert f"{app.HOME_EMOJI} " not in ret["body"]
    assert "LOCATION:https://russiabasket.ru/game/1083577?league=msl\n" in ret["body"]


def test_handler_defaults_without_params(apigw_event, rbf_api):
    event = copy.deepcopy(apigw_event)
    del event["params"], event["pathParameters"]

    ret = app.lambda_handler(event, None)

    assert ret["statusCode"] == 200
    assert rbf_api == [(app.HOME_TEAMID, app.get_season())]


def test_handler_falls_back_to_arena_name_without_arenas_file(apigw_event, rbf_api, arenas_file):
    arenas_file.unlink()

    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID)), None)

    assert ret["statusCode"] == 200
    assert "LOCATION:Дворец Спорта \"Динамо\"\n" in _event_of(ret["body"], 1083577)


def test_handler_falls_back_to_arena_name_for_unknown_arena(apigw_event, rbf_api, arenas_file):
    arenas_file.write_text(json.dumps({"arenas": []}), encoding="utf-8")

    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID)), None)

    assert "LOCATION:Дворец Спорта \"Динамо\"\n" in _event_of(ret["body"], 1083577)


def test_arenas_load_retries_after_failure(arenas_file):
    content = arenas_file.read_text(encoding="utf-8")
    arenas_file.unlink()
    assert app.get_arenas() == {}

    arenas_file.write_text(content, encoding="utf-8")
    assert list(app.get_arenas()) == [ARENA_ID]


def test_event_with_time(games, arenas_file):
    body = app.make_ics_calendar(TEAM_ID, [ARENA_ID], games)
    event = _event_of(body, 1083466)

    assert "DTSTART:20261001T130000Z\n" in event
    assert "DTEND:20261001T150000Z\n" in event
    assert f"SUMMARY:🏀 {app.VIDEO_EMOJI} Темп-СУМЗ vs Новосибирск\n" in event
    assert "Трансляция: https://embedded.slevel.ru/translations/" in event
    assert r"\nТурнир: Суперлига. Регулярный чемпионат\n" in event
    assert r"\nСсылка на матч: https://russiabasket.ru/game/1083466?league=msl" in event


def test_event_without_time_uses_local_date(games, arenas_file):
    # scheduledTime is 2026-11-02T00:00:00+07:00 - midnight in Novosibirsk
    event = _event_of(app.make_ics_calendar(TEAM_ID, [ARENA_ID], games), 1083506)

    assert "DTSTART;VALUE=DATE:20261102\n" in event
    assert "DTEND;VALUE=DATE:20261103\n" in event


def test_event_without_video_and_arena(games, arenas_file):
    event = _event_of(app.make_ics_calendar(TEAM_ID, [ARENA_ID], games), 1083833)

    assert r"Трансляция: Ссылка не опубликована :(\n" in event
    assert r"\nАрена: -\n" in event
    assert "LOCATION:https://russiabasket.ru/game/1083833?league=msl\n" in event


def test_event_with_score(games, arenas_file):
    game = copy.deepcopy(games[0])
    game["game"].update(showScore=True, score="97:101")
    game["ot"] = "2OT"

    event = app.make_ics_event(game, [ARENA_ID], "20260101T000000Z")

    assert f"SUMMARY:🏀 {app.VIDEO_EMOJI} Темп-СУМЗ 97:101 2OT Новосибирск\n" in event


def test_calendar_name_falls_back_to_team_id():
    assert "X-WR-CALNAME:БК 42\n" in app.make_ics_calendar(42, [ARENA_ID], [])


@pytest.mark.parametrize("now, season", [
    (datetime(2026, 7, 31), 2026),
    (datetime(2026, 8, 1), 2027),
    (datetime(2026, 12, 31), 2027),
    (datetime(2027, 1, 1), 2027),
])
def test_get_season(now, season):
    assert app.get_season(now) == season


def test_get_team_games_request(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {"items": [{"game": {"id": 1}}]}

    calls = []
    monkeypatch.setattr(app.requests, "get", lambda url, params: calls.append((url, params)) or Response())

    assert app.get_team_games(TEAM_ID, 2027) == [{"game": {"id": 1}}]
    assert calls == [("https://pro2.russiabasket.org/api/abc/comps/calendar", {
        "tag": "mcup,msl,vtb",
        "season": 2027,
        "teamId": TEAM_ID,
        "calendarType": -1,
        "maxResultCount": 1000,
    })]


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
