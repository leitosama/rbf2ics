from datetime import datetime, timedelta, timezone
import re
from typing import Optional, Tuple
import json
import logging
import os

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

def ics_escape(s: str) -> str:
    """Escapes a TEXT value per RFC 5545 (3.3.11)"""
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

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
        return ics_escape(arena.get("name") or "")
    return ics_escape(f"{known['name']}\n{known['address']}")

def get_video(s: str) -> Optional[str]:
    if not s:
        return None
    regexp = r"src=('|\")(https:|)\/\/([-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*))('|\")"
    search = re.search(regexp, s)
    logging.debug(f"Video: {s}")
    if search is None:
        return None
    return f"https://{search.group(3)}"

def get_broadcast(game: dict) -> Optional[str]:
    """Broadcast link: the iframe video of the game, else Kinopoisk if it is the game's TV"""
    video = get_video(game.get("video"))
    if video:
        return video
    if KINOPOISK_NAME in (game.get("tv") or "").lower():
        return KINOPOISK_URL
    return None

def get_datetime(game: dict) -> Tuple[str, str]:
    """DTSTART and DTEND values with their parameters, e.g. ";VALUE=DATE:20261102"

    scheduledTime is the local time of the game with its UTC offset. Games without
    time are all-day events on the local date, the others are converted to UTC.
    """
    d = datetime.fromisoformat(game["scheduledTime"])
    if not game.get("hasTime"):
        return f";VALUE=DATE:{d:%Y%m%d}", f";VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"

    d = d.astimezone(timezone.utc)
    return f":{d:%Y%m%dT%H%M%SZ}", f":{d + timedelta(hours=2):%Y%m%dT%H%M%SZ}"

def make_ics_headers(team_name: str, team_id: int):
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:RBF2ICS\nNAME:БК {team_name}\nX-WR-CALNAME:БК {team_name}\nDESCRIPTION:Календарь матчей РФБ ❤️ команды. Адрес для домашней площадки работает только для БК Новосибирск\nX-WR-CALDESC:RBF2ICS\nSOURCE;VALUE=URI:https://n8n.leito.tech/webhook/rbf2ics?teamId={team_id}\nREFRESH-INTERVAL;VALUE=DURATION:PT60M\nX-PUBLISHED-TTL:PT60M\nX-WR-TIMEZONE:UTC\nMETHOD:PUBLISH\nCALSCALE:GREGORIAN\n"

def make_ics_event(item: dict, arena_ids: list, dtstamp: str) -> str:
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
    video = get_broadcast(game) or "Ссылка не опубликована :("
    logging.debug(f"Video: {video}")

    if arena and int(arena["id"]) in arena_ids:
        watch_emoji = HOME_EMOJI
        location = get_arena_location(arena)
    else:
        watch_emoji = VIDEO_EMOJI
        location = link
    logging.debug(f"Location: {location}")

    score = " vs "
    if game.get("showScore") and game.get("score"):
        score = f" {game['score']}{' ' + item['ot'] if item.get('ot') else ''} "
    summary = ics_escape(f"🏀 {watch_emoji} {team1}{score}{team2}")
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
    return (
        f"BEGIN:VEVENT\nUID:{game['id']}@rbf2ics\nDTSTAMP:{dtstamp}\nSUMMARY:{summary}\n"
        f"DESCRIPTION:{ics_escape(description)}\nLOCATION:{location}\n"
        f"DTSTART{dtstart}\nDTEND{dtend}\nEND:VEVENT\n"
    )

def make_ics_calendar(team_id: int, arena_ids: list, team_games: list) -> str:
    dtstamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    ics_content = make_ics_headers(team_name=get_team_name(team_id, team_games), team_id=team_id)
    for item in team_games:
        ics_content += make_ics_event(item, arena_ids, dtstamp)

    ics_content += "END:VCALENDAR"
    return ics_content


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
