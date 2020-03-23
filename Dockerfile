FROM tiangolo/meinheld-gunicorn-flask:python3.6

COPY ForumMediaScraper/Dockerfile .

RUN apt-get update && \
    apt-get install -y git && \
    git clone --recurse-submodules https://github.com/jesseVDwolf/ForumMediaScraperREST.git app && \
    (cd app; /bin/bash -c "pip install ."; cd ForumMediaScraper; /bin/bash -c "pip install .")

RUN apt-get update && \
    apt-get -y install apt-transport-https \
        ca-certificates \
        curl \
        gnupg2 \
        software-properties-common && \
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg > /tmp/dkey; apt-key add /tmp/dkey && \
    add-apt-repository \
        "deb [arch=amd64] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
        $(lsb_release -cs) \
        stable" && \
    apt-get update && \
    apt-get -y install docker-ce=18.06.2~ce~3-0~debian
