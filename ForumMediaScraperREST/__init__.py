import os
import json
import base64
from flask import (
    Flask,
    request,
    Response
)
from pymongo.errors import AutoReconnect
from .FlaskController import FlaskController, MediaScraperStillRunning

app = Flask(__name__)
flask_controller = FlaskController(app=app)


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
        for run in flask_controller.database['Runs'].aggregate(pipeline=pipeline):
            for post in run['Posts']:
                gridfs_file = flask_controller.mongo_gridfs.get(post['MediaId'])
                post['MediaData'] = base64.b64encode(gridfs_file.read(size=-1)).decode('utf-8')

            run = flask_controller.object_to_string(doc=run)
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
    try:
        if request.method == 'GET':
            with open('{}/config.json'.format(os.path.dirname(os.path.abspath(__file__)))) as f:
                response_body['config'] = json.loads(f.read())
        if request.method == 'PUT':
            request_body = request.get_json()
            with open('{}/config.json'.format(os.path.dirname(os.path.abspath(__file__))), 'w') as f:
                f.write(json.dumps(request_body))
            flask_controller.validate_controller()
            response_body['config'] = request_body
    except FileNotFoundError:
        raise RuntimeError('No config file found on the server')
    except json.decoder.JSONDecodeError as decodeError:
        response_body.update({'success': False, 'error': {'type': 'json.decoder.JSONDecodeError', 'message': decodeError}})
        status = 400
    except MediaScraperStillRunning as runningJob:
        response_body.update({'success': False, 'error': {'type': 'MediaScraperStilRunning', 'message': runningJob.args[0]}})
        status = 409
    return Response(response=json.dumps(response_body), status=status, content_type='application/json')


if __name__ == '__main__':
    app.run(use_reloader=False, port=80)