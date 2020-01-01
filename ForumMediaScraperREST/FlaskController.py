import os
import pytz
import json
import gridfs
import atexit
import logging
from datetime import datetime, timedelta

from flask import Flask
from bson.objectid import ObjectId

from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from apscheduler.schedulers.background import BackgroundScheduler

from ForumMediaScraper import ForumMediaScraper, ScrapeConditionsNotMetException


class InvalidControllerException(Exception):
    """
    Raised during validation of the flask controller if
    one of the checks fails
    """
    pass


class InvalidConfigException(Exception):
    """
    Raised when validation of config fails
    """
    pass


class MediaScraperStillRunningException(Exception):
    """
    raised if a new configuration is send to the service
    but the media scraper is still running
    """
    pass


class FlaskController:
    """
    The flask controller has 3 tasks:
    1. Manage the webservice its internal state using the config.json file
    2. Manage external connections the webservice uses
    3. Manage the internal scheduler for running the scraper
    """
    SCRAPER_SHUTDOWN_BUFFER = 20

    MONGO_DEFAULT_URI = "mongodb://localhost:27017"
    MONGO_SERVER_TIMEOUT = 1

    WEBSERVICE_CONFIG_SETTINGS = {
        'SCRAPER_MAX_SCROLL_SECONDS': (int, 60),
        'SCRAPER_CREATE_SERVICE_LOG': (int, 0),
        'SCRAPER_HEADLESS_MODE': (int, 1),
        'SCRAPER_RUN_INTERVAL': (int, 300),
        'MONGO_INITDB_ROOT_USERNAME': (str, "admin"),
        'MONGO_INITDB_ROOT_PASSWORD': (str, "Noobmaster69"),
        'MONGO_INITDB_HOST': (str, "127.0.0.1"),
        'MONGO_INITDB_PORT': (int, 27017),
        'WEBDRIVER_EXECUTABLE_PATH': (str, ""),
        'WEBDRIVER_BROWSER_EXECUTABLE_PATH': (str, "")
    }

    def __init__(self, app: Flask):
        self._app = app
        self._app.logger.setLevel(logging.DEBUG)
        self.timezone = pytz.timezone('Europe/Berlin')

        with open('config.json', mode='w+') as f:
            config = {}
            for k, v in FlaskController.WEBSERVICE_CONFIG_SETTINGS.items():
                if os.getenv(k):
                    config[k] = os.getenv(k)
                else:
                    config[k] = v[1]
            f.write(json.dumps(config))

        mongo_args = self._get_mongo_uri(config)
        if mongo_args.get('error'):
            self._app.logger.error('Error creating mongo uri using config %s -> %s' % (str(config), mongo_args.get('error')))
            raise InvalidConfigException('Error creating mongo uri: %s' % mongo_args.get('error'))

        self._mongo_client = MongoClient(**mongo_args)
        self.mongo_database = self._mongo_client['9GagMedia']
        self.mongo_gridfs = gridfs.GridFS(self.mongo_database)

        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        atexit.register(lambda: self._scheduler.shutdown())

        self.forum_scraper_job = self._scheduler.add_job(
            func=self._start_scraper,
            trigger="interval",
            seconds=config.get('SCRAPER_RUN_INTERVAL')
        )

    def _start_scraper(self):
        """
        Function used by the apscheduler to run the scraper on a time based interval
        specified in the config.json file. Part of the webservice's config is used
        by the scraper as well.
        :return:
        """
        try:
            config = self.get_config()
            config = {k: v for (k, v) in config.items() if k != 'SCRAPER_RUN_INTERVAL'}
            config = {
                k: v for (k, v) in config.items() if not (
                    k in ['WEBDRIVER_BROWSER_EXECUTABLE_PATH', "WEBDRIVER_EXECUTABLE_PATH"] and v == ""
                )
            }
            for k in config.keys():
                if k in ['SCRAPER_HEADLESS_MODE', 'SCRAPER_CREATE_SERVICE_LOG']:
                    config[k] = bool(config[k])
            scraper = ForumMediaScraper(config)
            self._app.logger.info('Starting scraper job with config: %s' % str(config))
            scraper.run()
        except ServerSelectionTimeoutError as serverTimeout:
            self._app.logger.error('Could not connect to mongodb instance: %s' % str(serverTimeout))
        except ScrapeConditionsNotMetException as scrapeError:
            self._app.logger.error('Error during validation of the scrape conditions: %s' % str(scrapeError))

    @staticmethod
    def _get_mongo_uri(config: dict) -> dict:
        connection_args = {
            'host': None,
            'serverSelectionTimeoutMS': FlaskController.MONGO_SERVER_TIMEOUT
        }

        if config.get('MONGO_INITDB_HOST'):
            connection_args['host'] = 'mongodb://%s' % str(config.get('MONGO_INITDB_HOST'))

        if config.get('MONGO_INITDB_ROOT_USERNAME'):
            if not config.get('MONGO_INITDB_HOST'):
                return {'error': 'Specify mongo host if you use username and password auth'}

            connection_args['host'] = connection_args.get('host')[:10] + '{usr}:{pwd}@'.format(
                usr=config.get('MONGO_INITDB_ROOT_USERNAME'),
                pwd=config.get('MONGO_INITDB_ROOT_PASSWORD')
            ) + connection_args.get('host')[10:]

        if config.get('MONGO_INITDB_PORT'):
            connection_args.update({'port': config.get('MONGO_INITDB_PORT')})
        return connection_args

    @staticmethod
    def _validate_config(config: dict) -> dict:
        """
        Check if the configuration specified for the webservice is
        given in the correct format and given options are valid options
        :param config:
        :return:
        """
        if len(config.keys()) != len(FlaskController.WEBSERVICE_CONFIG_SETTINGS.keys()):
            return {'error': 'Missing required config options'}

        for k, v in config.items():
            if isinstance(v, dict):
                return {'error': 'Config can not have nested options'}
            if k not in FlaskController.WEBSERVICE_CONFIG_SETTINGS.keys():
                return {'error': 'Invalid config option %s' % str(k)}
            if not isinstance(v, FlaskController.WEBSERVICE_CONFIG_SETTINGS.get(k)[0]):
                return {'error': 'Config option %s is not the correct datatype' % str(k)}
            else:
                if isinstance(v, int) and k in ['SCRAPER_RUN_INTERVAL', 'SCRAPER_MAX_SCROLL_SECONDS']:
                    if v < FlaskController.WEBSERVICE_CONFIG_SETTINGS.get(k)[1]:
                        return {'error': 'Value of config option %s must be bigger then default %d' % (
                            str(k), FlaskController.WEBSERVICE_CONFIG_SETTINGS.get(k)[1])}
                elif isinstance(v, int) and k in ['SCRAPER_CREATE_SERVICE_LOG', 'SCRAPER_HEADLESS_MODE']:
                    if v not in [0, 1]:
                        return {'error': 'Boolean setting %s must have a value of either 0 or 1' % str(k)}
                else:
                    # value for this config option is not restricted
                    pass
        return config

    @staticmethod
    def get_config() -> dict:
        """
        Get config json from file
        :return:
        """
        with open('config.json') as f:
            return json.loads(f.read())

    def object_to_string(self, doc: dict) -> dict:
        """
        recursive function that checks all key value pairs and changes
        known object instances to strings in the correct format
        :param doc:
        :return:
        """
        for k, v in doc.items():
            if isinstance(v, datetime):
                doc.update({k: v.strftime("%Y-%m-%d %H:%M:%S")})
            if isinstance(v, ObjectId):
                doc.update({k: str(v)})
            if isinstance(v, list):
                for d in v:
                    self.object_to_string(d)
        return doc

    def update_internal_conf(self, config: dict) -> dict:
        """
        Update the webservice its internal state by updating config.json and
        rescheduling the scraper job if the run interval has changed. It returns
        the input config if it passes all validation. can raise InvalidConfigException
        and InvalidControllerException exceptions.
        :param config:
        :return:
        """
        with open('config.json', 'r+') as f:
            old = json.loads(f.read())
            if config == old:
                return config

            new = self._validate_config(config)
            if new.get('error'):
                self._app.logger.warning('Error while validating config %s -> %s' % (str(config), new.get('error')))
                raise InvalidConfigException(new.get('error'))

            if new.get('SCRAPER_RUN_INTERVAL') <= (FlaskController.SCRAPER_SHUTDOWN_BUFFER + new.get('SCRAPER_MAX_SCROLL_SECONDS')):
                self._app.logger.warning('Run interval must be bigger then buffer: %d + scroll seconds: %d' % (
                    FlaskController.SCRAPER_SHUTDOWN_BUFFER, new.get('MAX_SCROLL_SECONDS')))
                raise InvalidConfigException('Invalid run interval. Must be bigger than %d' % (
                        FlaskController.SCRAPER_SHUTDOWN_BUFFER + new.get('MAX_SCROLL_SECONDS')))

            mongo_args = self._get_mongo_uri(new)
            if mongo_args.get('error'):
                self._app.logger.error('Error creating mongo uri using config %s -> %s' % (str(config), mongo_args.get('error')))
                raise InvalidConfigException('Error creating mongo uri: %s' % mongo_args.get('error'))

            if not self.forum_scraper_job.trigger.interval == timedelta(seconds=new.get('SCRAPER_RUN_INTERVAL')):
                execution_duration = timedelta(seconds=(old.get('SCRAPER_MAX_SCROLL_SECONDS') + FlaskController.SCRAPER_SHUTDOWN_BUFFER))
                next_run_time = self.forum_scraper_job.next_run_time.astimezone(self.timezone) - timedelta(seconds=2)
                previous_run_time = next_run_time - timedelta(seconds=old.get('SCRAPER_RUN_INTERVAL'))
                now = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(self.timezone)

                if not ((previous_run_time + execution_duration) <= now <= next_run_time):
                    self._app.logger.warning('New configuration was send but MediaScraper is still running')
                    new.update({
                        'SCRAPER_RUN_INTERVAL': old['SCRAPER_RUN_INTERVAL'],
                        'SCRAPER_MAX_SCROLL_SECONDS': old['SCRAPER_MAX_SCROLL_SECONDS']
                    })
                    f.seek(0)
                    f.truncate()
                    f.write(json.dumps(new))
                    raise MediaScraperStillRunningException('Retry at {}'.format(
                        (previous_run_time + execution_duration).strftime("%Y-%m-%d %H:%M:%S")))

                self.forum_scraper_job = self.forum_scraper_job.reschedule(trigger='interval', seconds=new.get('SCRAPER_RUN_INTERVAL'))
                self._app.logger.info('Rescheduled job to run at interval %d with next run at %s' % (
                    new.get('SCRAPER_RUN_INTERVAL'), self.forum_scraper_job.next_run_time.astimezone(self.timezone).strftime("%Y-%m-%d %H:%M:%S")))

            f.seek(0)
            f.truncate()
            f.write(json.dumps(new))
            return new
