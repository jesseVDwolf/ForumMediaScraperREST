ForumMediaScraperREST
=====================
A simple Flask webserver that schedules the ForumMediascraper application. It also provides 
an interface to its internal configuration and the MongoDB instance the ForumMediascraper writes its data to.

Getting started
---------------
This project uses the [ForumMediaScraper](https://github.com/jesseVDwolf/ForumMediaScraper) as a submodule.
It uses the [apscheduler](https://pypi.org/project/APScheduler/2.1.2/) to schedule the ForumMediaScraper. Run
intervals and configuration for the scraper can all be configured via the REST interface provided by Flask.

**query**

The query endpoint is used to retrieve data from the MongoDB database.
```http
GET /query
```
| Parameter | Type | Description | Default |
| :--- | :--- | :--- | :---- |
| `limit` | `integer` | **Optional** Used for pagination, how many records to you want to retrieve | 5 |
| `offset`| `integer` | **Optional** Used for pagination, at what database row do you want to start | 0 |

*Response*
```javascript
{
  "success": true,
  "documents": [
      {
          "_id": "5dd01acf42d4da461c9da7f5",
          "StartScrapeTime": "2019-11-16 15:50:39",
          "EndScrapeTime": "2019-11-16 15:50:46",
          "PostsProcessed": 15,
          "StartPostId": "jsid-post-aqgGWWp",
          "Posts": [
              {
                  "_id: "5dd01ad042d4da461c9da7f8",
                  "ArticleId": "jsid-post-aqgGWWp",
                  "Title": "Five-year plans in communist country were like...",
                  "Section": "Funny",
                  "HourCreated": "3h",
                  "HourCreatedDate": "2019-11-16 12:50:40",
                  "Points": 3740,
                  "Comments": 375,
                  "PostShortLink": "/gag/aqgGWWp",
                  "ProcessTime": "2019-11-16 15:50:40",
                  "MediaId": "5dd01acf42d4da461c9da7f6",
                  "RunId": "5dd01acf42d4da461c9da7f5",
                  "MediaData": "/9j/4AAQSkZJRgABAQAAAQAB…NHn/wBT/wDnCVxmTd/b/9k="
              }
          ]
      }
  ]
}
```

**config**

There are also a set of operations that can be done on the config of the webservice. You can retrieve data with
GET and update the config with a PUT request. The PUT request it's response will be the new, updated config.
```http
GET /config
```

*Response*
```javascript
{
    "success": true,
    "config": {
        "SCRAPER_MAX_SCROLL_SECONDS": 60,
        "SCRAPER_CREATE_SERVICE_LOG": 0,
        "SCRAPER_HEADLESS_MODE": 1,
        "SCRAPER_RUN_INTERVAL": 300,
        "MONGO_INITDB_ROOT_USERNAME": "admin",
        "MONGO_INITDB_ROOT_PASSWORD": "Noobmaster69",
        "MONGO_INITDB_HOST": "mongo",
        "MONGO_INITDB_PORT": 27017,
        "WEBDRIVER_EXECUTABLE_PATH": "/usr/local/bin/drivers/geckodriver-linux",
        "WEBDRIVER_BROWSER_EXECUTABLE_PATH": ""
    }
}
```

```http
PUT /config
```

*Request body*
```javascript
{
  "MONGO_INITDB_ROOT_USERNAME": "admin",
  "MONGO_INITDB_ROOT_PASSWORD": "Noobmaster69",
  "MONGO_INITDB_HOST": "mongo",
  "MONGO_INITDB_PORT": 27017,
  "ForumMediaScraper": {
    "SCRAPER_RUN_INTERVAL": 60,
    "SCRAPER_MAX_SCROLL_SECONDS": 80,
    "SCRAPER_HEADLESS_MODE": 1
  }
}
```

*Response*
```javascript
{
    "success": true,
    "config": {
        "SCRAPER_MAX_SCROLL_SECONDS": 60,
        "SCRAPER_CREATE_SERVICE_LOG": 0,
        "SCRAPER_HEADLESS_MODE": 1,
        "SCRAPER_RUN_INTERVAL": 300,
        "MONGO_INITDB_ROOT_USERNAME": "admin",
        "MONGO_INITDB_ROOT_PASSWORD": "Noobmaster69",
        "MONGO_INITDB_HOST": "mongo",
        "MONGO_INITDB_PORT": 27017,
        "WEBDRIVER_EXECUTABLE_PATH": "/usr/local/bin/drivers/geckodriver-linux",
        "WEBDRIVER_BROWSER_EXECUTABLE_PATH": ""
    }
}
```


Setup
-----
Use git clone to download the repository (the recurse-submodules also downloads the ForumMediaScraper submodule):
```bash
$ git clone https://github.com/jesseVDwolf/ForumMediaScraperREST.git --recurse-submodules
```

**Local installation**

Install the flask application as a package using pip. Make sure you're in the same directory as the setup.py file:
```bash
$ pip install .
```

Run flask app from you're own python script:
```python
from ForumMediaScraperREST import app

app.run(host='0.0.0.0', port=5000)
```

**Run from docker**

To run the flask app from a docker container you have to follow the following steps. 
**Make Sure that when using docker-compose you change the docker-compose.yml file or when using docker run 
you change the -v to match your personal setup**

1. Build the docker image. Make sure you are in the same directory as the Dockerfile.
```bash
$ docker build -t myflaskapp:lastest .
```

2. Run the image:

Using docker-compose (make sure you are in the same directory as the docker-compose.yml file):
```bash
$ docker-compose up -d
```

Using docker run:
```bash
$ docker run -d --name myflaskap -p 5000:80 \
             -v ./drivers:/usr/local/bin/drivers \ 
             -e MONGO_INITDB_HOST=localhost \
             -e WEB_CONCURRENCY=1 \ 
             -e WEBDRIVER_EXECUTABLE_PATH=/usr/local/bin/drivers/geckodriver-linux \
             myflaskapp:latest
```