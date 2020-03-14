FROM tiangolo/meinheld-gunicorn-flask:python3.6

RUN apt-get update && \
    apt-get install -y git && \
    git clone --recurse-submodules https://github.com/jesseVDwolf/ForumMediaScraperREST.git app && \
    (cd app; /bin/bash -c "pip install ."; cd ForumMediaScraper; /bin/bash -c "pip install .")
