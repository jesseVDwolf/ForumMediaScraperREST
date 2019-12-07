import os
import sys
import pytz
import json
import gridfs
import atexit
import urllib.parse
from datetime import datetime, timedelta

from flask import Flask
from bson.objectid import ObjectId

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ServerSelectionTimeoutError

from apscheduler.job import Job
from apscheduler.schedulers.background import BackgroundScheduler

from ForumMediaScraper import ForumMediaScraper


class MediaScraperStillRunning(Exception):
    """
    raised if a new configuration is send to the service
    but the media scraper is still running
    """
    pass


class FlaskController:
    """
    DEFAULT_MAX_SCROLL_SECONDS: specified in ForumMediaScraper
    DEFAULT_SCRAPER_RUN_INTERVAL: seconds, can not be smaller than max_scroll_seconds + SCRAPER_START_SHUTDOWN_BUFFER
    SCRAPER_START_SHUTDOWN_BUFFER: seconds it takes for scraper to startup and shutdown
    """

    def __init__(self, app: Flask):
        self._app = app
        self.DEFAULT_MAX_SCROLL_SECONDS = 60
        self.DEFAULT_SCRAPER_RUN_INTERVAL = 120
        self.SCRAPER_START_SHUTDOWN_BUFFER = 20

        # database settings
        self.mongo_client = MongoClient
        self.mongo_gridfs = gridfs.GridFS
        self.database = Database

        # scheduler config
        self.scheduler = BackgroundScheduler()
        self.forum_scraper_schedule = Job
        atexit.register(lambda: self.scheduler.shutdown())

        # overwrite config with already existing environment variables
        with open('{}/config.json'.format(os.path.dirname(os.path.abspath(__file__))), mode='r+') as f:
            config = json.loads(f.read())
            config = self._update_config(config)
            f.seek(0)
            f.truncate()
            f.write(json.dumps(config))

        # validate necessary settings and services
        self.validate_controller()

        # set gecko driver environment variable for the ForumMediaScraper
        os.environ['GECKO_DRIVER_PATH'] = r'{}\ForumMediaScraper\ForumMediaScraper\bin\geckodriver.exe'.format(
            os.path.dirname(os.path.abspath(__file__))
        )

    def _start_scraper(self):
        """
        function used by the apscheduler to start the scraper based
        on the interval specified in the config.json file -> SCRAPER_RUN_INTERVAL
        """
        try:
            self.mongo_client.server_info()
            media_scraper = ForumMediaScraper()
            media_scraper.start_scraper()
        except ServerSelectionTimeoutError as serverTimeout:
            self._app.logger.error('Could not connect to mongodb instance before starting the ForumMediaScraper: {err}'.format(err=serverTimeout))

    def set_env(self, conf: dict):
        """
        recursive function that adds all key value pairs in the dictionary
        as environment variables using os.environ
        :param conf:
        :return:
        """
        for key, val in conf.items():
            if isinstance(conf[key], dict):
                self.set_env(conf[key])
            else:
                os.environ[key] = str(val)

    def _update_config(self, d: dict):
        """
        recursive function that updates a nested dict using
        the environment variables present in os.environ
        :param d:
        :return:
        """
        for k, v in d.items():
            if isinstance(v, dict):
                d[k] = self._update_config(d[k])
            else:
                if os.getenv(k):
                    d[k] = os.getenv(k)
        return d

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
            with open('{}/config.json'.format(os.path.dirname(os.path.abspath(__file__)))) as f:
                config = json.loads(f.read())

            # update environment for ForumMediaScraper
            self.set_env(conf=config)

            # create mongodb client instance
            self.mongo_client = MongoClient('mongodb://{usr}:{pwd}@{host}'.format(
                usr=urllib.parse.quote_plus(os.environ.get('MONGO_INITDB_ROOT_USERNAME')),
                pwd=urllib.parse.quote_plus(os.environ.get('MONGO_INITDB_ROOT_PASSWORD')),
                host=urllib.parse.quote_plus(os.environ.get('MONGO_INITDB_HOST'))),
                serverSelectionTimeoutMS=os.environ.get('MAX_SERVER_SELECTION_DELAY')
            )

            # force a connection on a request to check if server is online
            self.mongo_client.server_info()
            self.database = self.mongo_client['9GagMedia']
            self.mongo_gridfs = gridfs.GridFS(database=self.database)

            # start scheduler if not already running
            if not self.scheduler.running:
                self.scheduler.start()

            # get run_interval and max_scroll_settings loaded from config or stick to default
            run_interval = self.DEFAULT_SCRAPER_RUN_INTERVAL
            if os.environ.get('SCRAPER_RUN_INTERVAL'):
                run_interval = int(os.environ.get('SCRAPER_RUN_INTERVAL'))

            max_scroll_seconds = self.DEFAULT_MAX_SCROLL_SECONDS
            if os.environ.get('MAX_SCROLL_SECONDS'):
                max_scroll_seconds = int(os.environ.get('MAX_SCROLL_SECONDS'))

            # make sure run_interval is correct
            if run_interval <= (self.SCRAPER_START_SHUTDOWN_BUFFER + max_scroll_seconds):
                self._app.logger.warning('Incorrect run interval in config file, using default')
                run_interval = self.DEFAULT_SCRAPER_RUN_INTERVAL

            # add job if not already created
            if isinstance(self.forum_scraper_schedule, type):
                self._app.logger.info('Creating ')
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
                execution_duration = timedelta(seconds=(max_scroll_seconds + self.SCRAPER_START_SHUTDOWN_BUFFER))
                next_run_time = self.forum_scraper_schedule.next_run_time - timedelta(seconds=2)  # small buffer
                previous_run_time = next_run_time - timedelta(seconds=run_interval)

                # check if request comes in in a time frame where we're sure no job is running
                if not ((previous_run_time + execution_duration) <= timezone.localize(datetime.now()) <= next_run_time):
                    self._app.logger.warning('New configuration was send but MediaScraper is still running')
                    raise MediaScraperStillRunning('Retry at {}'.format(
                        timezone.localize((datetime.utcnow() + execution_duration)).strftime("%Y-%m-%d %H:%M:%S"))
                    )

                # reschedule job
                self._app.logger.info('Rescheduled the ForumMediaScraper job to run at {} second intervals'.format(run_interval))
                self.forum_scraper_schedule.reschedule(trigger='interval', seconds=run_interval)

        except FileNotFoundError:
            self._app.logger.error('Could not find a config.json file, can not start the server')
            sys.exit(1)
        except json.decoder.JSONDecodeError as decodeError:
            self._app.logger.error('Could not parse the config.json file, is it correct json: {err}'.format(err=decodeError))
            sys.exit(1)
        except ServerSelectionTimeoutError as serverTimeout:
            self._app.logger.warning('Could not create connection to mongoDB server, is MONGO_INITDB_HOST set up correctly?: {err}'.format(err=serverTimeout))
