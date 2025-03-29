from datetime import datetime, timedelta, date, timezone
import re
from typing import Tuple
import json
import logging

import requests

HOME_ARENAID = 11745
HOME_ADDRESS = r'Север\\nУчительская улица\, 61\, Новосибирск\, Новосибирская область\, Россия\, 630110'
HOME_TEAMID = 3204
HOME_EMOJI = "🏠"
VIDEO_EMOJI = "🛜"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def get_team_info(team_id: int):
    team_info = json.loads(requests.get(f"https://org.infobasket.su/Widget/TeamInfo/{team_id}?format=json").text, object_hook=lambda d: SimpleNamespace(**d))
    team_info.json = team_info
    return team_info

def get_team_games(team_id: int):
    team_games = json.loads(requests.get(f"https://org.infobasket.su/Widget/TeamGames/{team_id}?format=json").text, object_hook=lambda d: SimpleNamespace(**d))
    for game in team_games:
        game.json = game
    return team_games

def get_video(s: str) -> str:
    if not s:
        return "-"
    regexp = r"src=('|\")(https:|)\/\/([-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*))('|\")"
    search = re.search(regexp, s)
    logger.debug(f"VideoID: {s}")
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

def make_ics_event(item, team_id: int) -> str:
    logging.debug(f"GameID: {item.json.GameID}")
    link = f"https://competitions.russiabasket.ru/games/{item.json.GameID}"
    if item.json.VideoID:
        video = get_video(item.json.VideoID)
    else:
        video = "-"
    logging.debug(f"VideoID: {video}")
    watch_emoji = None   
    if item.json.ArenaId == HOME_ARENAID and item.json.TeamAid == team_id:
        watch_emoji = HOME_EMOJI
        location = HOME_ADDRESS
    else:
        watch_emoji = VIDEO_EMOJI
        location = video
    summary = f"🏀 {watch_emoji} {item.json.ShortTeamNameAru} vs {item.json.ShortTeamNameBru}"
    logging.debug(f"Summary: {summary}")
    dtstart, dtend = get_datetime(item)
    logging.debug(f"{dtstart} - {dtend}")
    description = f"Трансляция: {video}\nАрена: {item.json.ArenaRu}\nСсылка на матч: {link}"
    # logging.debug(description)
    ics_content = f"BEGIN:VEVENT\nSUMMARY:{summary}\nDESCRIPTION:{description}\nLOCATION:{location}\nDTSTART;{dtstart}\nDTEND;{dtend}\nEND:VEVENT\n"

    return ics_content

def make_ics_calendar(team_id: int, team_info, team_games) -> str:
    ics_content = make_ics_headers(team_name=team_info.json.CurrentTeamName.CompTeamShortNameRu, team_id=team_id)
    for item in team_games:
        ics_content += make_ics_event(item,team_id)

    ics_content += "END:VCALENDAR"
    return ics_content

# for local
# team_id = 3204
# team_info = get_team_info(team_id)
# team_games = get_team_games(team_id)

# for n8n
# team_id = _('Webhook').item.json.query.teamId
# team_info = _('TeamInfo').item
# team_games = _input.all()

# ics_calendar = make_ics_calendar(team_id,team_info,team_games)
# return [{'json':{'text':ics_calendar}}]