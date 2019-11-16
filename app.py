import os
import sys
import json
from flask import Flask


MONGO_INITDB_ROOT_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_INITDB_ROOT_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')

app = Flask(__name__)

if not MONGO_INITDB_ROOT_USERNAME or MONGO_INITDB_ROOT_PASSWORD:
    app.logger.error('Environment not setup correctly, are all environment variables set up?')
    sys.exit(1)


# query route that provides an interface to the MongoDB database
@app.route('/query', methods=['GET'])
def query():
    return 'Query'


# config route that provides an interface to the internal configuration of the flask webservice
@app.route('/config', methods=['POST', 'GET', 'PUT'])
def config():
    return 'Config'


if __name__ == '__main__':
    app.run()
