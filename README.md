# rbf2ics
RBF calendar

## API
https://org.infobasket.su/  
https://org.infobasket.su/Widget/TeamGames/3204?format=json  
https://org.infobasket.su/Widget/TeamInfo/3204?format=json  

## Architecture
```
rbf2ics.yc.leito.tech/ # Yandex API GW
├── / # frontend page (S3)
├── /{file+} # files for frontend page (S3)
└── /ics/{team_id}/{arena_ids}.ics # Yandex Serverless functions
```

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
rbf2ics$ cd rbf2ics && python -c "import json, app; print(app.lambda_handler(json.load(open('../events/event.json')), None)['body'])"
```

### Tests
Tests are defined in the `tests` folder in this project. Use PIP to install the test dependencies and run tests.

```bash
rbf2ics$ pip install -r tests/requirements.txt
rbf2ics$ python -m pytest tests/unit -v
```

## VideoID
Все трансляции беру из iframe'ов