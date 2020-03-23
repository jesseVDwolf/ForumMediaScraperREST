import os
import json
import docker
import atexit
from pathlib import Path
from flask import Flask
from gridfs import GridFS
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient
from ForumMediaScraper.Scraper import ScraperConfig
from apscheduler.schedulers.background import BackgroundScheduler

_SCRAPER_CONTAINER_IMAGE = 'jvanderwolf/forum-media-scraper:0.1'
_SCRAPER_CONTAINER_NAME = 'forum-scraper'
_SCRAPER_NETWORK_NAME = 'forum-media-net'

_WEBSERVICE_SETTINGS = {
    'SCRAPER_SHUTDOWN_BUFFER': 20,
    'SCRAPER_RUN_INTERVAL': 10
}


class ContainerManager:

    def __init__(self, app: Flask, config: ScraperConfig):
        self._logger = app.logger
        self._config = config
        self._client = docker.from_env()
        if not [image for image in self._client.images.list() if _SCRAPER_CONTAINER_IMAGE in image.attrs['RepoTags']]:
            self._client.images.build(
                path=os.getcwd(),
                tag=_SCRAPER_CONTAINER_IMAGE
            )

    def run(self):
        if [container for container in self._client.containers.list() if container.name == _SCRAPER_CONTAINER_NAME]:
            self._logger.warn("Container is still running, start request denied")
            return

        config = {}
        for key, value in self._config: config[key] = value
        path = Path(os.getcwd())
        self._client.containers.run(
            image=_SCRAPER_CONTAINER_IMAGE,
            shm_size='2G',
            remove=True,
            name=_SCRAPER_CONTAINER_NAME,
            network='{parent}_{netname}'.format(parent=path.name.lower(), netname=_SCRAPER_NETWORK_NAME),
            environment=config,
            detach=True,
            command='/usr/local/bin/python /scraper/entrypoint.py'
        )


class FlaskController:
    """
    The flask controller has 3 tasks:
    1. Manage the webservice its internal state using the config.json file
    2. Manage external connections the webservice uses
    3. Manage the internal scheduler for running the scraper
    """

    def __init__(self, app: Flask, config: ScraperConfig):
        self.logger = app.logger

        self.mongo_client = MongoClient(**config.get_mongo_config())
        self.mongo_database = self.mongo_client['ForumMediaData']
        self.mongo_gridfs = GridFS(database=self.mongo_database)

        self._app = app
        self._container_manager = ContainerManager(app, config)
        self._scraper_config = config.update(_WEBSERVICE_SETTINGS)
        self._config_file = 'config.json'
        self._datetime_format = "%Y-%m-%d %H:%M:%S"
        self._service_config = self.load_config()

        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        atexit.register(lambda: self._scheduler.shutdown())

        """self._scraper_job = self._scheduler.add_job(
            func=self._container_manager.run,
            trigger="interval",
            seconds=config['SCRAPER_RUN_INTERVAL']
        )"""

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
