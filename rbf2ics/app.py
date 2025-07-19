from datetime import datetime, timedelta, date
import json
import re
from typing import Tuple, List, Dict
from datetime import datetime, timedelta, timezone
import requests


HOME_ARENAID = 11745
HOME_ADDRESS = 'Север\\nУчительская улица\, 61\, Новосибирск\, Новосибирская область\, Россия\, 630110'
HOME_EMOJI = "🏠"
VIDEO_EMOJI = "🛜"

def get_video(s: str) -> str:
    pattern = r"src='//([^\\]+)'"
    return f"https://{re.search(pattern, s).group(1)}"

def get_dt(e: dict) -> Tuple[str, str]:
    d = e['GameDateTimeMoscow']
    tzid = "Europe/Moscow"
    moscow_offset = timedelta(hours=3)
    moscow_tz = timezone(moscow_offset)
    if d is None:
        d = e['GameLocalDate']
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

def get_events(j: str) -> List[Dict]:
    d = json.loads(j)
    events = []
    for e in d:
        print(e['GameID'])
        video = get_video(e['VideoID'])
        watch_emoji = None  
        event_location = None
        if e['ArenaId'] == HOME_ARENAID:
            watch_emoji = HOME_EMOJI
            event_location = HOME_ADDRESS
        else:
            watch_emoji = VIDEO_EMOJI
            event_location = video

        event_summary = f"🏀 {watch_emoji} {e['ShortTeamNameAru']} vs {e['ShortTeamNameBru']}"
        event_dtstart, event_dtend = get_dt(e)
        event_description = f"Трансляция: {video}\nАрена: {e['ArenaRu']}"
        events.append({
            'summary': event_summary,
            'description': event_description,
            'location': event_location,
            'dtstart': event_dtstart,
            'dtend': event_dtend
        })
    return events


def generate_ics(events, file_name='calendar.ics'):
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\nREFRESH-INTERVAL;VALUE=DURATION:PT60M\n"

    for event in events:
        ics_content += f"""BEGIN:VEVENT
SUMMARY:{event['summary']}
DESCRIPTION:{event['description']}
LOCATION:{event['location']}
DTSTART;{event['dtstart']}
DTEND;{event['dtend']}
END:VEVENT
"""

    ics_content += "END:VCALENDAR"

    return ics_content


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
    nsk = None
    try:
        nsk = requests.get("https://org.infobasket.su/Widget/TeamGames/3204?format=json").text
    except requests.RequestException as e:
        print(e)
        raise e
    events = get_events(nsk)
        
    ics_content = generate_ics(events)

    return {
        "statusCode": 200,
        "body": {}
    }
