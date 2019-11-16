import os
import sys
import json
import base64
import gridfs
import atexit
import datetime
import urllib.parse
from flask import (
    Flask,
    request,
    Response
)
from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.errors import (
    ServerSelectionTimeoutError,
    AutoReconnect
)
from apscheduler.schedulers.background import BackgroundScheduler
from ForumMediaScraper.ForumMediaScraper import ForumMediaScraper

app = Flask(__name__)


def start_scraper():
    """
    function used by the apscheduler to start the scraper based
    on the interval specified in the config.json file -> SCRAPER_RUN_INTERVAL
    """
    media_scraper = ForumMediaScraper()
    media_scraper.start_scraper()


def set_env(conf: dict):
    """
    recursive function that adds all key value pairs in the dictionary
    as environment variables using os.environ
    :param conf:
    :return:
    """
    for key, val in conf.items():
        if isinstance(conf[key], dict):
            set_env(conf[key])
        else:
            os.environ[key] = str(val)


def object_to_string(doc: dict) -> dict:
    """
    recursive function that checks all key value pairs and changes
    known object instances to strings in the correct format
    :param doc:
    :return:
    """
    for k, v in doc.items():
        if isinstance(v, datetime.datetime):
            doc.update({k: v.strftime("%Y-%m-%d %H:%M:%S")})
        if isinstance(v, ObjectId):
            doc.update({k: str(v)})
        if isinstance(v, list):
            for d in v:
                object_to_string(d)
    return doc


try:
    # read config file
    with open('config.json') as f:
        config = json.loads(f.read())

    # setup environment for ForumMediaScraper
    set_env(conf=config)

    mongo_client = MongoClient('mongodb://{usr}:{pwd}@127.0.0.1'.format(
        usr=urllib.parse.quote_plus(config.get('MONGO_INITDB_ROOT_USERNAME')),
        pwd=urllib.parse.quote_plus(config.get('MONGO_INITDB_ROOT_PASSWORD'))),
        serverSelectionTimeoutMS=config.get('MAX_SERVER_SELECTION_DELAY')
    )
    # force a connection on a request to check if server is online
    mongo_client.server_info()
    database = mongo_client['9GagMedia']
    mongo_gridfs = gridfs.GridFS(database=database)

    # setup scheduler for the forum media scraper
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=start_scraper, trigger="interval", seconds=config.get('SCRAPER_RUN_INTERVAL'))
    scheduler.start()

    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

except FileNotFoundError:
    app.logger.error('Could not find a config.json file, can not start the server')
    sys.exit(1)
except json.decoder.JSONDecodeError as decodeError:
    app.logger.error('Could not parse the config.json file, is it correct json: {err}'.format(err=decodeError))
    sys.exit(1)
except ServerSelectionTimeoutError as serverTimeout:
    app.logger.error('Could not create connection to mongoDB server: {err}'.format(err=serverTimeout))
    sys.exit(1)


# query route that provides an interface to the MongoDB database
@app.route('/query', methods=['GET'])
def query():
    status = 200
    body = {'success': True, 'documents': []}
    limit = request.args.get('limit') if request.args.get('limit') else 5
    offset = request.args.get('offset') if request.args.get('offset') else 0
    try:
        # create mongodb aggregation pipeline
        pipeline = [
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
        # build response json body
        for run in database['Runs'].aggregate(pipeline=pipeline):
            for post in run['Posts']:
                gridfs_file = mongo_gridfs.get(post['MediaId'])
                post['MediaData'] = base64.b64encode(gridfs_file.read(size=-1)).decode('utf-8')

            run = object_to_string(doc=run)
            body['documents'].append(run)
    except AutoReconnect as MongoError:
        app.logger.warning('Error reconnecting to the mongo database: {err}'.format(err=MongoError))
        body.update({'success': False, 'error': {'type': 'pymongo.errors.AutoReconnect', 'message': MongoError}})
        status = 500
    return Response(response=json.dumps(body), status=status, content_type='application/json')


# config route that provides an interface to the internal configuration of the flask webservice
@app.route('/config', methods=['GET', 'PUT'])
def config():
    status = 200
    response_body = {'success': True, 'config': {}}

    if request.method == 'GET':
        with open('config.json') as f:
            response_body['config'] = json.loads(f.read())

    if request.method == 'PUT':
        request_body = request.get_json()
        with open('config.json', 'w') as f:
            f.write(json.dumps(request_body))
            set_env(conf=request_body)
            response_body['config'] = request_body
    return Response(response=json.dumps(response_body), status=status, content_type='application/json')


if __name__ == '__main__':
    app.run(use_reloader=False)
