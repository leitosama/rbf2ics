from datetime import date, datetime, timedelta, timezone
import re
from typing import Optional, Tuple, Union
import json
import logging
import os

from icalendar import Calendar, Event, vDuration
import requests

class RequestFailedException(Exception):
    def __init__(self, url: str, status_code: int, response_text: str):
        super().__init__(f"Request to {url} failed with status code {status_code}: {response_text}")
        self.url = url
        self.status_code = status_code
        self.response_text = response_text

HOME_ARENAID = 11745
HOME_TEAMID = 3204
HOME_EMOJI = "🏠"
VIDEO_EMOJI = "🛜"
RBF_API_URL = "https://pro2.russiabasket.org".rstrip("/")
# Public address of the function behind API Gateway, the SOURCE of the calendar
BASE_URL = "https://rbf2ics.yc.leito.tech"
PRODID = "-//leito.tech//rbf2ics//RU"
CALENDAR_DESCRIPTION = "Календарь матчей РФБ ❤️ команды. Адрес для домашней площадки работает только для БК Новосибирск"
REFRESH_INTERVAL = timedelta(hours=1)
GAME_DURATION = timedelta(hours=2)
# Competition tags of the calendar request, the API returns no games without them
LEAGUES = ["mcup", "msl", "vtb"]
# -1 - all games: scheduled, online and finished (see /api/abc/comps/calendar-types)
CALENDAR_TYPE = -1
# The API returns 10 games by default
MAX_RESULT_COUNT = 1000
# VTB United League games are broadcast on Kinopoisk, which has no per-game links:
# game["tv"] looks like "Кинопоиск (🎙️: Дмитрий Колинов)", so it gets the league page
KINOPOISK_NAME = "кинопоиск"
KINOPOISK_URL = "https://hd.kinopoisk.ru/sport/competition/37370/"
GAME_URL = "https://russiabasket.ru/game"
# Names shared by several teams of the leagues: in event summaries they get the team region
AMBIGUOUS_TEAM_NAMES = {"Динамо"}
MOSCOW_TZ = timezone(timedelta(hours=3))
# arenas.json lives in the frontend bucket (data/arenas.json) and is mounted into the
# function read-only. Override with ARENAS_PATH for local runs and tests.
ARENAS_PATH = os.environ.get("ARENAS_PATH", "/function/storage/data/arenas.json")

logging.basicConfig(level=logging.DEBUG)

_arenas = None

def get_arenas() -> dict:
    """Arenas by id from arenas.json, read once per function instance.

    A failed read is logged and not cached: the calendar still renders
    (with arena names from the RBF API), and the next request retries.
    """
    global _arenas
    if _arenas is None:
        try:
            with open(ARENAS_PATH, encoding="utf-8") as f:
                _arenas = {int(arena["id"]): arena for arena in json.load(f)["arenas"]}
        except (OSError, ValueError, KeyError, TypeError):
            logging.exception(f"Failed to load arenas from {ARENAS_PATH}")
            return {}
    return _arenas

def get_season(now: Optional[datetime] = None) -> int:
    """Season is named by the year it ends in and starts in August: Aug 2026 - Jul 2027 is 2027"""
    now = now or datetime.now(MOSCOW_TZ)
    return now.year + 1 if now.month >= 8 else now.year

def get_team_games(team_id: int, season: int) -> list:
    r = requests.get(f"{RBF_API_URL}/api/abc/comps/calendar", params={
        "tag": ",".join(LEAGUES),
        "season": season,
        "teamId": team_id,
        "calendarType": CALENDAR_TYPE,
        "maxResultCount": MAX_RESULT_COUNT,
    })
    if r.status_code != 200:
        raise RequestFailedException(url=r.url, status_code=r.status_code, response_text=r.text)
    return r.json()["items"] or []

def get_full_team_name(team: Optional[dict]) -> str:
    """Team name with its region, e.g. "Динамо (Уфа)"

    The API has no full team name: name and shortName are the same ("Динамо"),
    so teams with the same name are told apart by their region.
    """
    team = team or {}
    name = team.get("name") or team.get("shortName") or ""
    region = team.get("regionName")
    if name and region and region != name:
        return f"{name} ({region})"
    return name

def get_summary_team_name(team: Optional[dict]) -> str:
    """Team name for event summaries, with the region only for ambiguous names"""
    team = team or {}
    name = team.get("name") or team.get("shortName") or ""
    return get_full_team_name(team) if name in AMBIGUOUS_TEAM_NAMES else name

def get_team_name(team_id: int, games: list) -> str:
    for item in games:
        for team in (item.get("team1"), item.get("team2")):
            if team and team.get("teamId") == team_id:
                return get_full_team_name(team) or str(team_id)
    return str(team_id)

def get_arena_location(arena: dict) -> str:
    known = get_arenas().get(int(arena["id"]))
    if known is None:
        return arena.get("name") or ""
    return f"{known['name']}\n{known['address']}"

def get_video(game: dict) -> Optional[str]:
    s = game.get("video") or ""
    regexp = r"src=('|\")(https:|)\/\/([-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*))('|\")"
    search = re.search(regexp, s)
    logging.debug(f"Video: {s}")
    if search is not None:
        return f"https://{search.group(3)}"
    if KINOPOISK_NAME in (game.get("tv") or "").lower():
        return KINOPOISK_URL
    return None

def get_datetime(game: dict) -> Tuple[Union[date, datetime], Union[date, datetime]]:
    """DTSTART and DTEND of a game

    scheduledTime is the local time of the game with its UTC offset. Games without
    time are all-day events on the local date, the others are converted to UTC.
    """
    d = datetime.fromisoformat(game["scheduledTime"])
    if not game.get("hasTime"):
        return d.date(), d.date() + timedelta(days=1)

    d = d.astimezone(timezone.utc)
    return d, d + GAME_DURATION

def get_calendar_url(team_id: int, arena_ids: list) -> str:
    return f"{BASE_URL}/ics/{team_id}/{'_'.join(str(aid) for aid in arena_ids)}.ics"

def make_calendar_headers(team_name: str, team_id: int, arena_ids: list) -> Calendar:
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("name", f"БК {team_name}")
    cal.add("x-wr-calname", f"БК {team_name}")
    cal.add("description", CALENDAR_DESCRIPTION)
    cal.add("x-wr-caldesc", CALENDAR_DESCRIPTION)
    cal.add("source", get_calendar_url(team_id, arena_ids), parameters={"VALUE": "URI"})
    cal.add("refresh-interval", REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
    # Unknown X- properties are not typed by icalendar: a timedelta would be written as "1:00:00"
    cal.add("x-published-ttl", vDuration(REFRESH_INTERVAL))
    cal.add("x-wr-timezone", "UTC")
    return cal

def make_event(item: dict, arena_ids: list, dtstamp: datetime) -> Event:
    game = item["game"]
    league = item.get("league") or {}
    comp = item.get("comp") or {}
    arena = item.get("arena")
    team1 = get_summary_team_name(item.get("team1"))
    team2 = get_summary_team_name(item.get("team2"))
    logging.debug(f"GameID: {game['id']}")

    link = f"{GAME_URL}/{game['id']}"
    if league.get("tag"):
        link += f"?league={league['tag']}"
    video = get_video(game) or "Ссылка не опубликована :("
    logging.debug(f"Video: {video}")

    if arena and int(arena["id"]) in arena_ids:
        watch_emoji = HOME_EMOJI
    else:
        watch_emoji = VIDEO_EMOJI
    location = get_arena_location(arena) if arena else ""
    logging.debug(f"Location: {location}")

    score = " vs "
    if game.get("showScore") and game.get("score"):
        score = f" {game['score']}{' ' + item['ot'] if item.get('ot') else ''} "
    summary = f"🏀 {watch_emoji} {team1}{score}{team2}"
    logging.debug(f"Summary: {summary}")

    dtstart, dtend = get_datetime(game)
    logging.debug(f"{dtstart} - {dtend}")

    tournament = ". ".join(n for n in (league.get("name"), comp.get("name")) if n)
    description = "\n".join([
        f"Трансляция: {video}",
        f"Турнир: {tournament}",
        f"Арена: {(arena or {}).get('name') or '-'}",
        f"Ссылка на матч: {link}",
    ])

    event = Event()
    event.add("uid", f"{game['id']}@rbf2ics")
    event.add("dtstamp", dtstamp)
    event.add("summary", summary)
    event.add("description", description)
    if location:
        event.add("location", location)
    event.add("url", link)
    event.add("dtstart", dtstart)
    event.add("dtend", dtend)
    return event

def make_calendar(team_id: int, arena_ids: list, team_games: list) -> Calendar:
    dtstamp = datetime.now(timezone.utc).replace(microsecond=0)
    cal = make_calendar_headers(get_team_name(team_id, team_games), team_id, arena_ids)
    for item in team_games:
        cal.add_component(make_event(item, arena_ids, dtstamp))
    return cal

def make_ics_calendar(team_id: int, arena_ids: list, team_games: list) -> str:
    return make_calendar(team_id, arena_ids, team_games).to_ical().decode("utf-8")


def lambda_handler(event, context):
    """Yandex Cloud Function handler

    Parameters
    ----------
    event: dict, required
        Yandex API Gateway request (x-yc-apigateway-integration: cloud_functions)

        Event doc: https://yandex.cloud/en/docs/functions/concepts/function-invoke#request

    context: object, required
        Function invocation context

        Context doc: https://yandex.cloud/en/docs/functions/lang/python/context

    Returns
    ------
    HTTP response: dict

        Return doc: https://yandex.cloud/en/docs/functions/concepts/function-invoke#response
    """
    # Path parameters of /ics/{team_id}/{arena_ids}.ics. API Gateway sends them both
    # under "params" and "pathParameters"; either may be missing in local events.
    params = event.get("params") or event.get("pathParameters") or {}
    team_id = int(params.get("team_id", HOME_TEAMID))
    arena_ids = str(params.get("arena_ids", HOME_ARENAID))
    # Games in any of these arenas are home games: the user can go and watch them
    arena_ids = [int(aid) for aid in arena_ids.split("_") if aid.isdigit()] or [HOME_ARENAID]
    team_games = get_team_games(team_id, get_season())
    ics_content = make_ics_calendar(team_id, arena_ids, team_games)
    logging.debug(ics_content)

    return {
        "statusCode": 200,
        "headers":{
            "Content-Type": "text/calendar; charset=utf-8",
            "Content-Disposition": 'attachment; filename="rbf2ics.ics"'
        },
        "body": ics_content
    }


if __name__ == "__main__":
    # for local
    print(make_ics_calendar(HOME_TEAMID, [HOME_ARENAID], get_team_games(HOME_TEAMID, get_season())))
