import json
import base64
from pymongo.errors import AutoReconnect
from ForumMediaScraper.Scraper import ScraperConfig
from ForumMediaScraperREST.Controller import FlaskController
from flask import (
    Flask,
    request,
    Response
)

config = ScraperConfig({
    'WEBDRIVER_EXECUTABLE_PATH': './drivers/geckodriver-win.exe',
    'MONGO_INITDB_ROOT_USERNAME': 'admin',
    'MONGO_INITDB_ROOT_PASSWORD': 'password123',
    'SCRAPER_CREATE_LOGFILE': True,
    'SCRAPER_HEADLESS_MODE': False,
    'SCRAPER_MAX_SCROLL_SECONDS': 40,
    'WEBDRIVER_BROWSER_EXECUTABLE_PATH': 'C:\\Program Files\\Mozilla Firefox\\firefox.exe'
})

app = Flask(__name__)
controller = FlaskController(app, config)


@app.route('/query', methods=['GET'])
def query():
    status = 200
    body = {'success': True, 'documents': []}
    limit = request.args.get('limit') if request.args.get('limit') else 5
    offset = request.args.get('offset') if request.args.get('offset') else 0
    try:
        pipeline = [
            {"$sort": {"StartScrapeTime": -1}},
            {"$skip": int(offset)},
            {"$limit": int(limit)},
            {"$lookup":
                {
                    "from": "Posts",
                    "localField": "_id",
                    "foreignField": "RunId",
                    "as": "Posts"
                }
            }
        ]
        cursor = controller.mongo_database['Runs'].aggregate(pipeline)
        for run in cursor:
            for post in run['Posts']:
                file = controller.mongo_gridfs.get(post['MediaId'])
                post['file'] = base64.b64encode(file.read(size=-1)).decode('utf-8')
            run = controller.convert_objects(run)
            body['documents'].append(run)
    except AutoReconnect as MongoError:
        app.logger.warning('Error reconnecting to the mongo database: {err}'.format(err=MongoError))
        body.update({'success': False, 'error': {'type': 'pymongo.errors.AutoReconnect', 'message': MongoError}})
        status = 500
    return Response(response=json.dumps(body), status=status, content_type='application/json')


@app.route('/config', methods=['GET', 'PUT'])
def config():
    status = 200
    response_body = {'success': True}
    try:
        if request.method == 'GET':
            response_body['config'] = controller.load_config()
        elif request.method == 'PUT':
            request_body = request.get_json(silent=True)
            if request_body is None:
                raise Exception('Failed to parse json')
            new_config = controller.put_config(request_body)
            response_body['config'] = new_config
    except Exception as err:
        app.logger.warning('Request failed with reason: %s' % str(err))
        status = 500
    return Response(response=json.dumps(response_body), status=status, content_type='application/json')


if __name__ == '__main__':
    app.run(use_reloader=False, port=80)
