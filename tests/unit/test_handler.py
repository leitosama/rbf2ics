import copy
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from icalendar import Calendar
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
    return Calendar.from_ical(body).walk("VEVENT")


def _event_of(body, game_id):
    return next(e for e in _events(body) if e["UID"] == f"{game_id}@rbf2ics")


def _summaries(body):
    return [str(e["SUMMARY"]) for e in _events(body)]


def _home_count(body):
    return sum(s.startswith(f"🏀 {app.HOME_EMOJI} ") for s in _summaries(body))


def _make_event(item):
    return app.make_event(item, [ARENA_ID], datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_handler_returns_calendar(apigw_event, rbf_api):
    ret = app.lambda_handler(apigw_event, None)

    assert ret["statusCode"] == 200
    assert ret["headers"]["Content-Type"].startswith("text/calendar")
    assert ret["body"].startswith("BEGIN:VCALENDAR\r\n")
    assert ret["body"].endswith("END:VCALENDAR\r\n")
    cal = Calendar.from_ical(ret["body"])
    assert len(cal.walk("VEVENT")) == 26
    assert cal["X-WR-CALNAME"] == cal["NAME"] == "БК Новосибирск"
    assert cal["SOURCE"] == "https://rbf2ics.yc.leito.tech/ics/3204/11745.ics"
    assert rbf_api == [(3204, app.get_season())]


def test_calendar_is_rfc5545_content(apigw_event, rbf_api):
    body = app.lambda_handler(apigw_event, None)["body"]

    lines = body.split("\r\n")
    assert "\n" not in "".join(lines)
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    assert "PRODID:-//leito.tech//rbf2ics//RU" in lines
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H" in lines
    assert "SOURCE;VALUE=URI:https://rbf2ics.yc.leito.tech/ics/3204/11745.ics" in lines
    assert "X-PUBLISHED-TTL:PT1H" in lines
    cal = Calendar.from_ical(body)
    assert cal["DESCRIPTION"] == cal["X-WR-CALDESC"] == app.CALENDAR_DESCRIPTION


@pytest.mark.parametrize("keys", [("params",), ("pathParameters",)])
def test_handler_uses_path_parameters(apigw_event, rbf_api, keys):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID), keys), None)

    assert rbf_api == [(TEAM_ID, app.get_season())]
    assert _home_count(ret["body"]) == 1
    assert r"LOCATION:Test\; arena\nStreet\, 1" in ret["body"]
    assert _event_of(ret["body"], 1083577)["LOCATION"] == "Test; arena\nStreet, 1"
    assert Calendar.from_ical(ret["body"])["SOURCE"] == f"{app.BASE_URL}/ics/{TEAM_ID}/{ARENA_ID}.ics"


def test_handler_all_arenas_are_home(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, f"11745_{ARENA_ID}"), None)

    # 13 games in СКК Север and 1 in ARENA_ID
    assert _home_count(ret["body"]) == 14
    assert Calendar.from_ical(ret["body"])["SOURCE"] == f"{app.BASE_URL}/ics/{TEAM_ID}/11745_{ARENA_ID}.ics"


def test_handler_other_arena_is_not_home(apigw_event, rbf_api):
    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, "1"), None)

    assert _home_count(ret["body"]) == 0
    # A known arena keeps its address in away games too
    event = _event_of(ret["body"], 1083577)
    assert event["LOCATION"] == "Test; arena\nStreet, 1"
    assert event["URL"].startswith("https://embedded.slevel.ru/translations/")


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
    assert _event_of(ret["body"], 1083577)["LOCATION"] == "Дворец Спорта \"Динамо\""


def test_handler_falls_back_to_arena_name_for_unknown_arena(apigw_event, rbf_api, arenas_file):
    arenas_file.write_text(json.dumps({"arenas": []}), encoding="utf-8")

    ret = app.lambda_handler(_event(apigw_event, TEAM_ID, str(ARENA_ID)), None)

    assert _event_of(ret["body"], 1083577)["LOCATION"] == "Дворец Спорта \"Динамо\""


def test_arenas_load_retries_after_failure(arenas_file):
    content = arenas_file.read_text(encoding="utf-8")
    arenas_file.unlink()
    assert app.get_arenas() == {}

    arenas_file.write_text(content, encoding="utf-8")
    assert list(app.get_arenas()) == [ARENA_ID]


def test_event_with_time(games, arenas_file):
    body = app.make_ics_calendar(TEAM_ID, [ARENA_ID], games)
    event = _event_of(body, 1083466)

    assert event.decoded("DTSTART") == datetime(2026, 10, 1, 13, tzinfo=timezone.utc)
    assert event.decoded("DTEND") == datetime(2026, 10, 1, 15, tzinfo=timezone.utc)
    assert "DTSTART:20261001T130000Z" in body.split("\r\n")
    assert event["SUMMARY"] == f"🏀 {app.VIDEO_EMOJI} Темп-СУМЗ vs Новосибирск"
    assert event["LOCATION"] == "СК БК \"Темп-СУМЗ\""
    assert event["URL"] == "https://embedded.slevel.ru/translations/N2M3MTFlMjU0Y2IyNzU2MjRhZTQwMzRhNzA1YWExNWE6NDU5MTAxMTo0Ojo/embed7"
    description = str(event["DESCRIPTION"])
    assert description.startswith("Трансляция: https://embedded.slevel.ru/translations/")
    assert "\nТурнир: Суперлига. Регулярный чемпионат\n" in description
    assert description.endswith("\nСсылка на матч: https://russiabasket.ru/game/1083466?league=msl")


def test_event_without_time_uses_local_date(games, arenas_file):
    # scheduledTime is 2026-11-02T00:00:00+07:00 - midnight in Novosibirsk
    body = app.make_ics_calendar(TEAM_ID, [ARENA_ID], games)
    event = _event_of(body, 1083506)

    assert event.decoded("DTSTART") == date(2026, 11, 2)
    assert event.decoded("DTEND") == date(2026, 11, 3)
    assert "DTSTART;VALUE=DATE:20261102" in body.split("\r\n")


def test_event_without_video_and_arena(games, arenas_file):
    event = _event_of(app.make_ics_calendar(TEAM_ID, [ARENA_ID], games), 1083833)

    assert "Трансляция: Ссылка не опубликована :(\n" in event["DESCRIPTION"]
    assert "\nАрена: -\n" in event["DESCRIPTION"]
    assert "LOCATION" not in event
    # No broadcast: the event links to the game page
    assert event["URL"] == "https://russiabasket.ru/game/1083833?league=msl"


def test_event_on_kinopoisk_links_to_league_page(games, arenas_file):
    game = copy.deepcopy(games[0])
    game["game"].update(video=None, tv="Кинопоиск (🎙️: Дмитрий Колинов)")

    event = _make_event(game)

    assert f"Трансляция: {app.KINOPOISK_URL}\n" in event["DESCRIPTION"]
    assert event["URL"] == app.KINOPOISK_URL


def test_event_video_wins_over_kinopoisk(games, arenas_file):
    game = copy.deepcopy(games[0])
    game["game"].update(tv="Кинопоиск")

    event = _make_event(game)

    assert event["DESCRIPTION"].startswith("Трансляция: https://embedded.slevel.ru/translations/")


def test_home_event_is_busy(games, arenas_file):
    event = _event_of(app.make_ics_calendar(TEAM_ID, [ARENA_ID], games), 1083577)

    assert event["SUMMARY"].startswith(f"🏀 {app.HOME_EMOJI} ")
    assert event["TRANSP"] == "OPAQUE"
    assert event["CATEGORIES"].cats == [app.HOME_CATEGORY, "Суперлига"]


def test_online_event_is_free(games, arenas_file):
    event = _event_of(app.make_ics_calendar(TEAM_ID, [ARENA_ID], games), 1083466)

    assert event["SUMMARY"].startswith(f"🏀 {app.VIDEO_EMOJI} ")
    assert event["TRANSP"] == "TRANSPARENT"
    assert event["CATEGORIES"].cats == [app.ONLINE_CATEGORY, "Суперлига"]


def test_event_without_arena_and_league_is_online(games, arenas_file):
    game = copy.deepcopy(games[0])
    game["arena"] = None
    game["league"] = None

    event = _make_event(game)

    assert event["TRANSP"] == "TRANSPARENT"
    assert event["CATEGORIES"].cats == [app.ONLINE_CATEGORY]


def test_calendar_color():
    cal = app.make_calendar(TEAM_ID, [ARENA_ID], [])

    assert cal["COLOR"] == app.CALENDAR_COLOR
    assert cal["X-APPLE-CALENDAR-COLOR"] == app.APPLE_CALENDAR_COLOR


def test_event_with_score(games, arenas_file):
    game = copy.deepcopy(games[0])
    game["game"].update(showScore=True, score="97:101")
    game["ot"] = "2OT"

    event = _make_event(game)

    assert event["SUMMARY"] == f"🏀 {app.VIDEO_EMOJI} Темп-СУМЗ 97:101 2OT Новосибирск"


def test_summary_has_region_of_ambiguous_team(games, arenas_file):
    body = app.make_ics_calendar(TEAM_ID, [ARENA_ID], games)

    summaries = _summaries(body)
    assert f"🏀 {app.VIDEO_EMOJI} Динамо (Уфа) vs Новосибирск" in summaries
    assert f"🏀 {app.VIDEO_EMOJI} Динамо (Грозный) vs Новосибирск" in summaries
    assert not any("ЦСКА-2 (" in s for s in summaries)


@pytest.mark.parametrize("team, name", [
    ({"name": "Динамо", "shortName": "Динамо", "regionName": "Уфа"}, "Динамо (Уфа)"),
    ({"name": "ЦСКА-2", "regionName": "Москва"}, "ЦСКА-2 (Москва)"),
    ({"name": "Новосибирск", "regionName": "Новосибирск"}, "Новосибирск"),
    ({"shortName": "ЧБК", "regionName": None}, "ЧБК"),
    (None, ""),
])
def test_get_full_team_name(team, name):
    assert app.get_full_team_name(team) == name


def test_calendar_name_has_team_region(games):
    for item in games:
        for key in ("team1", "team2"):
            if item[key]["teamId"] == TEAM_ID:
                item[key]["regionName"] = "Бердск"

    assert app.make_calendar(TEAM_ID, [ARENA_ID], games)["X-WR-CALNAME"] == "БК Новосибирск (Бердск)"


def test_calendar_name_falls_back_to_team_id():
    assert app.make_calendar(42, [ARENA_ID], [])["X-WR-CALNAME"] == "БК 42"


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


def test_arenas_json_is_valid():
    arenas = json.loads(ARENAS_JSON.read_text(encoding="utf-8"))["arenas"]

    ids = [arena["id"] for arena in arenas]
    assert all(type(aid) is int for aid in ids)
    assert len(ids) == len(set(ids))
    for arena in arenas:
        for field in ("name", "address", "city"):
            assert isinstance(arena[field], str) and arena[field].strip(), (arena["id"], field)
