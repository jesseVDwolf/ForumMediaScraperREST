import os
import json
from flask import Flask
from gridfs import GridFS
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient
from ForumMediaScraper.Scraper import ScraperConfig

_WEBSERVICE_SETTINGS = {
    'SCRAPER_SHUTDOWN_BUFFER': 20,
    'SCRAPER_RUN_INTERVAL': 120
}


class FlaskController:
    """
    The flask controller has 3 tasks:
    1. Manage the webservice its internal state using the config.json file
    2. Manage external connections the webservice uses
    3. Manage the internal scheduler for running the scraper
    """

    def __init__(self, app: Flask, config: ScraperConfig):
        self.logger = app.logger
        self.timezone = pytz.timezone('Europe/Berlin')

        self.mongo_client = MongoClient(**config.get_mongo_config())
        self.mongo_database = self.mongo_client['ForumMediaData']
        self.mongo_gridfs = GridFS(database=self.mongo_database)

        self._app = app
        self._scraper_config = config.update(_WEBSERVICE_SETTINGS)
        self._config_file = 'config.json'
        self._datetime_format = "%Y-%m-%d %H:%M:%S"
        self._service_config = self.load_config()

    def load_config(self):
        config = {}
        mode = 'r'
        if not os.path.isfile(self._config_file):
            mode = 'w+'
        with open(self._config_file, mode=mode) as f:
            if mode == 'w+':
                for key, value in self._scraper_config:
                    if os.getenv(key):
                        config[key] = os.getenv(key)
                    else:
                        config[key] = value
                f.write(json.dumps(config))
            f.seek(0)
            return json.loads(f.read())

    def put_config(self, new: dict):
        config = self.load_config()
        config.update(new)
        with open(self._config_file, mode='w+') as f:
            f.write(json.dumps(config))
            return config

    def convert_objects(self, doc: dict):
        for key, value in doc.items():
            if isinstance(value, datetime):
                doc[key] = value.strftime(self._datetime_format)
            elif isinstance(value, ObjectId):
                doc[key] = str(value)
            elif isinstance(value, list):
                for document in value:
                    self.convert_objects(document)
        return doc
