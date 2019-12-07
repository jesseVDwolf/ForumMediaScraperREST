FROM tiangolo/meinheld-gunicorn-flask:python3.6

RUN apt-get update && \
    apt-get install -y git && \
    git clone https://github.com/jesseVDwolf/ForumMediaScraperREST.git --recurse-submodules app && \
    (cd app; /bin/bash -c "pip install ."; cd ForumMediaScraper; /bin/bash -c "pip install .")