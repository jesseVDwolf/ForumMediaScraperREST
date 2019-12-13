import os
import sys
import pytz
import json
import gridfs
import atexit
from datetime import datetime, timedelta

from flask import Flask
from bson.objectid import ObjectId

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ServerSelectionTimeoutError

from apscheduler.job import Job
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

    """
    _SCRAPER_SHUTDOWN_BUFFER = 20

    _MONGO_SERVER_TIMEOUT = 1  # seconds. Can be so little since connection is localhost

    # configuration options with default data type and value
    _WEBSERVICE_CONFIG_SETTINGS = {
        'SCRAPER_MAX_SCROLL_SECONDS': (int, 60),
        'SCRAPER_CREATE_SERVICE_LOG': (int, 0),
        'SCRAPER_HEADLESS_MODE': (int, 1),
        'SCRAPER_RUN_INTERVAL': (int, 120),
        'MONGO_INITDB_ROOT_USERNAME': (str, "admin"),
        'MONGO_INITDB_ROOT_PASSWORD': (str, "Noobmaster69"),
        'MONGO_INITDB_HOST': (str, "127.0.0.1"),
        'MONGO_INITDB_PORT': (int, 27017),
        'WEBDRIVER_EXECUTABLE_PATH': (str, ""),
        'WEBDRIVER_BROWSER_EXECUTABLE_PATH': (str, "")
    }

    def __init__(self, app: Flask):
        self._app = app

        # database settings
        self._mongo_client = MongoClient
        self.mongo_gridfs = gridfs.GridFS
        self.mongo_database = Database

        # scheduler config
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.forum_scraper_schedule = Job
        atexit.register(lambda: self.scheduler.shutdown())

        try:
            # create default config with already existing environment variables
            with open('config.json', mode='w+') as f:
                config = {}
                for k, v in FlaskController._WEBSERVICE_CONFIG_SETTINGS.items():
                    if os.getenv(k):
                        config[k] = os.getenv(k)
                    else:
                        config[k] = v[1]
                f.write(json.dumps(config))

            # validate necessary settings and services
            self.validate_controller()
        except IOError as io:
            self._app.logger.error('Failed to create config file %s' % str(io))
            sys.exit(1)
        except ServerSelectionTimeoutError as timeoutError:
            self._app.logger.error('Could not connect to mongoDB server, is MONGO_INITDB_HOST set up correctly?: %s' % str(timeoutError))

    def _start_scraper(self):
        """
        function used by the apscheduler to start the scraper based
        on the interval specified in the config.json file -> SCRAPER_RUN_INTERVAL
        """
        try:
            self.validate_controller()
            with open('config.json') as f:
                config = {k: v for (k, v) in json.loads(f.read()).items() if k != 'SCRAPER_RUN_INTERVAL'}
                config = {
                    k: v for (k, v) in config.items() if not (
                        k in ['WEBDRIVER_BROWSER_EXECUTABLE_PATH', "WEBDRIVER_EXECUTABLE_PATH"] and v == ""
                    )
                }
                for k in config.keys():
                    if k in ['SCRAPER_HEADLESS_MODE', 'SCRAPER_CREATE_SERVICE_LOG']:
                        config[k] = bool(config[k])
            scraper = ForumMediaScraper(config=config)
            scraper.run()
        except ServerSelectionTimeoutError as serverTimeout:
            self._app.logger.error('Could not connect to mongodb instance before starting the ForumMediaScraper: %s' % str(serverTimeout))
        except ScrapeConditionsNotMetException as scrapeError:
            self._app.logger.error('Error during validation of the scrape conditions: %s' % str(scrapeError))

    @staticmethod
    def _validate_config(d: dict):
        """
        Check if the configuration specified for the webservice is
        given in the correct format and given options are valid options
        :param d:
        :return:
        """
        for k, v in d.items():
            if isinstance(v, dict):
                raise InvalidConfigException('Config can not have nested options')
            if k not in FlaskController._WEBSERVICE_CONFIG_SETTINGS.keys():
                raise InvalidConfigException('Invalid config option %s' % str(k))
            if not isinstance(v, FlaskController._WEBSERVICE_CONFIG_SETTINGS.get(k)[0]):
                raise InvalidConfigException('Config option %s is not the correct datatype' % str(k))

    def get_config(self):
        try:
            if os.access('config.json', os.R_OK):
                with open('config.json') as f:
                    return json.loads(f.read())
            else:
                raise IOError('Access check on config file failed')
        except IOError as err:
            self._app.logger.error('Failed to update config file: %s' % str(err))
            return {}

    def put_config(self, config: dict):
        try:
            self._validate_config(config)
            if os.access('config.json', os.W_OK):
                with open('config.json', 'w') as f:
                    f.write(json.dumps(config))
            else:
                raise IOError('Access check on config file failed')
            return config
        except IOError as err:
            self._app.logger.error('Failed to update config file: %s' % str(err))
            return {}
        except InvalidConfigException as invalidConfig:
            self._app.logger.error('Failed to update config file: %s' % str(invalidConfig))
            return {}

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

    def validate_controller(self):
        try:
            # read config file
            with open('config.json') as f:
                config = json.loads(f.read())

            #  create mongo client to interact with local mongoDB instance
            connection_args = {
                'host': None,
                'serverSelectionTimeoutMS': FlaskController._MONGO_SERVER_TIMEOUT
            }

            if config.get('MONGO_INITDB_HOST'):
                connection_args['host'] = 'mongodb://%s' % str(config.get('MONGO_INITDB_HOST'))

            if config.get('MONGO_INITDB_ROOT_USERNAME'):
                if not config.get('MONGO_INITDB_HOST'):
                    raise InvalidControllerException('Specify mongo host if you use username and password auth')

                connection_args['host'] = connection_args.get('host')[:10] + '{usr}:{pwd}@'.format(
                    usr=config.get('MONGO_INITDB_ROOT_USERNAME'),
                    pwd=config.get('MONGO_INITDB_ROOT_PASSWORD')
                ) + connection_args.get('host')[10:]

            if config.get('MONGO_INITDB_PORT'):
                connection_args.update({'port': config.get('MONGO_INITDB_PORT')})
            self._mongo_client = MongoClient(**connection_args)

            # force a connection on a request to check if server is online
            self._mongo_client.server_info()
            self.mongo_database = self._mongo_client['9GagMedia']
            self.mongo_gridfs = gridfs.GridFS(database=self.mongo_database)

            # get run_interval and max_scroll_settings loaded from config or stick to default
            run_interval = FlaskController._WEBSERVICE_CONFIG_SETTINGS.get('SCRAPER_RUN_INTERVAL')[1]
            if os.environ.get('SCRAPER_RUN_INTERVAL'):
                run_interval = config.get('SCRAPER_RUN_INTERVAL')

            max_scroll_seconds = FlaskController._WEBSERVICE_CONFIG_SETTINGS.get('SCRAPER_MAX_SCROLL_SECONDS')[1]
            if os.environ.get('MAX_SCROLL_SECONDS'):
                max_scroll_seconds = config.get('MAX_SCROLL_SECONDS')

            # make sure run_interval is correct
            if run_interval <= (FlaskController._SCRAPER_SHUTDOWN_BUFFER + max_scroll_seconds):
                self._app.logger.warning('Incorrect run interval in config file, using default')
                run_interval = FlaskController._WEBSERVICE_CONFIG_SETTINGS.get('SCRAPER_RUN_INTERVAL')[1]

            # add job if not already created
            if isinstance(self.forum_scraper_schedule, type):
                self._app.logger.info('Creating schedule job for ForumMediaScraper')
                self.forum_scraper_schedule = self.scheduler.add_job(
                    func=self._start_scraper,
                    trigger="interval",
                    seconds=run_interval
                )

            # change job schedule interval if config changed
            if not self.forum_scraper_schedule.trigger.interval == timedelta(seconds=run_interval):
                """ 
                If ForumMediaScraper is currently running, send message back to client to wait and retry later.
                Use SCRAPER_START_SHUTDOWN_BUFFER, the MAX_SCROLL_SECONDS, the current run_interval and the 
                schedule's last run time to check if job is still running
                """

                # get important timestamps for is_running check using Europe/Berlin timezone
                timezone = pytz.timezone('Europe/Berlin')
                execution_duration = timedelta(seconds=(max_scroll_seconds + FlaskController._SCRAPER_SHUTDOWN_BUFFER))
                next_run_time = self.forum_scraper_schedule.next_run_time - timedelta(seconds=2)  # small buffer
                previous_run_time = next_run_time - timedelta(seconds=run_interval)

                # check if request comes in in a time frame where we're sure no job is running
                if not ((previous_run_time + execution_duration) <= timezone.localize(datetime.now()) <= next_run_time):
                    self._app.logger.warning('New configuration was send but MediaScraper is still running')
                    raise MediaScraperStillRunningException('Retry at {}'.format(
                        timezone.localize((datetime.utcnow() + execution_duration)).strftime("%Y-%m-%d %H:%M:%S"))
                    )

                # reschedule job
                self._app.logger.info(
                    'Rescheduled the ForumMediaScraper job to run at {} second intervals'.format(run_interval))
                self.forum_scraper_schedule.reschedule(trigger='interval', seconds=run_interval)

        except ServerSelectionTimeoutError as serverTimeout:
            self._app.logger.warning(
                'Could not create connection to mongoDB server, is MONGO_INITDB_HOST set up correctly?: %s' % str(
                    serverTimeout))
            raise InvalidControllerException

