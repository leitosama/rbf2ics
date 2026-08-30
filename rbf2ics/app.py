from datetime import datetime, timedelta, date, timezone
import re
from typing import Tuple
from types import SimpleNamespace
import json
import logging

import requests

class RequestFailedException(Exception):
    def __init__(self, url: str, status_code: int, response_text: str):
        super().__init__(f"Request to {url} failed with status code {status_code}: {response_text}")
        self.url = url
        self.status_code = status_code
        self.response_text = response_text

ARENAS = {
    11745: {
        "address": r'Север\nУчительская улица\, 61\, Новосибирск\, Новосибирская область\, Россия\, 630110'
    },
    11926: {
        "address": r'ДС Динамо\nУлица Лавочкина\, 32\, Москва\, Россия\, 125581'
    }
}

HOME_ARENAID = 11745
HOME_TEAMID = 3204
HOME_EMOJI = "🏠"
VIDEO_EMOJI = "🛜"
RBF_API_URL = "https://org.infobasket.su".rstrip("/")

logging.basicConfig(level=logging.DEBUG)

def get_team_info(team_id: int) -> dict:
    team_info_r = requests.get(f"{RBF_API_URL}/Widget/TeamInfo/{team_id}?format=json")
    if team_info_r.status_code != 200:
        raise RequestFailedException(
            url=team_info_r.url,
            status_code=team_info_r.status_code,
            response_text=team_info_r.text
        )
    team_info = json.loads(team_info_r.text, object_hook=lambda d: SimpleNamespace(**d))
    team_info.json = team_info
    return team_info

def get_team_games(team_id: int) -> dict:
    team_games_r = requests.get(f"{RBF_API_URL}/Widget/TeamGames/{team_id}?format=json")
    if team_games_r.status_code != 200:
        raise RequestFailedException(
            url=team_games_r.url,
            status_code=team_games_r.status_code,
            response_text=team_games_r.text
        )
    team_games = json.loads(team_games_r.text, object_hook=lambda d: SimpleNamespace(**d))

    for game in team_games:
        game.json = game
    return team_games

def get_video(s: str) -> str:
    if not s:
        return "-"
    regexp = r"src=('|\")(https:|)\/\/([-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*))('|\")"
    search = re.search(regexp, s)
    logging.debug(f"VideoID: {s}")
    return f"https://{search.group(3)}"

def get_datetime(item) -> Tuple[str, str]:
    d = item.json.GameDateTimeMoscow
    tzid = "Europe/Moscow"
    moscow_tz = timezone(timedelta(hours=3))
    if d is None:
        d = item.json.GameLocalDate
        d = date.fromtimestamp(int(d[6:-2])/1000)
        dtstart=d.strftime('%Y%m%d')
        dtend=(d+timedelta(days=1)).strftime('%Y%m%d')
        event_dtstart = f"VALUE=DATE:{dtstart}"
        event_dtend = f"VALUE=DATE:{dtend}"
        return event_dtstart, event_dtend

    d = datetime.fromtimestamp(int(d[6:-2])/1000,moscow_tz)

    dtstart=d.strftime('%Y%m%dT%H%M%S')

    event_dtstart = f"TZID={tzid}:{dtstart}"
    dtend=(d+timedelta(hours=2)).strftime('%Y%m%dT%H%M%S')
    event_dtend = f"TZID={tzid}:{dtend}"
    return event_dtstart, event_dtend

def make_ics_headers(team_name: str, team_id: int):
    return f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:RBF2ICS\nNAME:БК {team_name}\nX-WR-CALNAME:БК {team_name}\nDESCRIPTION:Календарь матчей РФБ ❤️ команды. Адрес для домашней площадки работает только для БК Новосибирск\nX-WR-CALDESC:RBF2ICS\nSOURCE;VALUE=URI:https://n8n.leito.tech/webhook/rbf2ics?teamId={team_id}\nREFRESH-INTERVAL;VALUE=DURATION:PT60M\nX-PUBLISHED-TTL:PT60M\nX-WR-TIMEZONE:UTC\nMETHOD:PUBLISH\nCALSCALE:GREGORIAN\n"

def make_ics_event(item, team_id: int, arena_id: int) -> str:
    logging.debug(f"GameID: {item.json.GameID}")
    link = f"https://competitions.russiabasket.ru/games/{item.json.GameID}"
    if item.json.VideoID:
        video = get_video(item.json.VideoID)
    else:
        video = "Ссылка не опубликована :("
    logging.debug(f"VideoID: {video}")
    watch_emoji = None
    if int(item.json.ArenaId) == arena_id and int(item.json.TeamAid) == int(team_id):
        watch_emoji = HOME_EMOJI
        location = ARENAS[arena_id]['address']
    else:
        watch_emoji = VIDEO_EMOJI
        if video == "Ссылка не опубликована :(":
            location = video
        else:
            location = link

    logging.debug(f"Location: {location}")
    summary = f"🏀 {watch_emoji} {item.json.ShortTeamNameAru} vs {item.json.ShortTeamNameBru}"
    logging.debug(f"Summary: {summary}")
    dtstart, dtend = get_datetime(item)
    logging.debug(f"{dtstart} - {dtend}")
    description = f"Трансляция: {video}\\nАрена: {item.json.ArenaRu}\\nСсылка на матч: {link}"
    ics_content = f"BEGIN:VEVENT\nSUMMARY:{summary}\nDESCRIPTION:{description}\nLOCATION:{location}\nDTSTART;{dtstart}\nDTEND;{dtend}\nEND:VEVENT\n"

    return ics_content

def make_ics_calendar(team_id: int, arena_id: int, team_info: dict, team_games: dict) -> str:
    ics_content = make_ics_headers(team_name=team_info.json.CurrentTeamName.CompTeamShortNameRu, team_id=team_id)
    for item in team_games:
        ics_content += make_ics_event(item,team_id,arena_id)

    ics_content += "END:VCALENDAR"
    return ics_content




# for n8n
# team_id = _('Webhook').item.json.query.teamId
# team_info = _('TeamInfo').item
# team_games = _input.all()
# return [{'json':{'text':ics_calendar}}]

if __name__ == "__main__":
    # for local
    team_id = HOME_TEAMID
    arena_id = HOME_ARENAID
    team_info = get_team_info(team_id)
    team_games = get_team_games(team_id)
    
    ics_calendar = make_ics_calendar(team_id,arena_id, team_info,team_games)
    print(ics_calendar)


def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format

        Event doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict

        Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """
    # query_params = event.get("queryStringParameters") or {}
    params = event.get("param", {})
    team_id = int(params.get("team_id", HOME_TEAMID))
    arena_ids = params.get("arena_ids", f"{HOME_ARENAID}.ics")
    arena_ids = [int(aid) for aid in arena_ids.strip(".ics").split("_") if aid.isdigit()]
    team_info = get_team_info(team_id)
    team_games = get_team_games(team_id)
    # TODO: I just use the first arena_id for now, but we can support multiple arenas in the future
    ics_content = make_ics_calendar(team_id, arena_ids[0], team_info, team_games)
    logging.debug(ics_content)
    

    return {
        "statusCode": 200,
        "headers":{
            "Content-Type": "text/calendar; charset=utf-8",
            "Content-Disposition": 'attachment; filename="rbf2ics.ics"'
        },
        "body": ics_content
    }
