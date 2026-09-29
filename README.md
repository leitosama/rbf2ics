# rbf2ics
RBF calendar

## API
Swagger: https://basket.sportoteka.org/swagger/v1/swagger.json  
Calendar of a team: https://pro2.russiabasket.org/api/abc/comps/calendar?tag=mcup,msl,vtb&season=2027&teamId=3204&calendarType=-1&maxResultCount=1000

- `tag` - competitions (`LEAGUES` in `app.py`), no games are returned without it.
- `season` - the year the season ends in, a new season starts in August (Aug 2026 - Jul 2027 is `2027`).
- `calendarType` - `-1` for all games (see `/api/abc/comps/calendar-types`).
- `maxResultCount` - only 10 games are returned by default.

Game page: `https://russiabasket.ru/game/{game.id}?league={league.tag}`.
Time of a game is `game.scheduledTime` (local time with UTC offset), events are in UTC.
Games with `game.hasTime = false` have no time: they are all-day events on the date of `game.scheduledTime`.

## Architecture
```
rbf2ics.yc.leito.tech/ # Yandex API GW
├── / # frontend page (S3)
├── /{file+} # files for frontend page (S3)
│   └── /data/arenas.json # shared data, also mounted into the function
└── /ics/{team_id}/{arena_ids}.ics # Yandex Serverless functions, games in any of `arena_ids` (joined with `_`) are home games
```

### Shared data
`frontend/data/` is uploaded to the bucket with the frontend and holds data used by both sides.
The frontend fetches it over HTTP; the function gets the `data/` prefix of the bucket mounted
read-only at `/function/storage/data` (mount name is `mount` in `.deploy/function.json`).

`arenas.json` — arenas with a known address (used as `LOCATION` of home games):
```json
{"arenas": [{"id": 11745, "name": "СКК Север", "address": "Учительская улица, 61, ...", "city": "Новосибирск"}]}
```
`id` is `arena.id` from the calendar API. Values are plain text, the function escapes them for ICS.

## Development
- `rbf2ics` - Code for the Yandex Cloud Function (entrypoint `app.lambda_handler`).
- `events` - Sample API Gateway events for invoking the function locally.
- `frontend` - Static frontend page served from Object Storage.
- `tests` - Unit tests for the application code.
- `.deploy` - Terraform and function config for deploying to Yandex Cloud.

### Run locally
The handler is a plain Python function that takes an API Gateway event (a well-known JSON document) and a context, so no emulator is needed:

```bash
rbf2ics$ pip install -r rbf2ics/requirements.txt
rbf2ics$ cd rbf2ics && ARENAS_PATH=../frontend/data/arenas.json python -c "import json, app; print(app.lambda_handler(json.load(open('../events/event.json')), None)['body'])"
```

### Tests
Tests are defined in the `tests` folder in this project. Use PIP to install the test dependencies and run tests.

```bash
rbf2ics$ pip install -r tests/requirements.txt
rbf2ics$ python -m pytest tests/unit -v
```

## VideoID
Все трансляции беру из iframe'ов