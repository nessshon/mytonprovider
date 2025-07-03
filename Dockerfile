# Dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git curl wget virtualenv python3 python3-pip fio && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/mytonprovider
RUN git clone --recursive https://github.com/igroman787/mytonprovider.git . && \
    git submodule update --init --recursive

RUN virtualenv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -r resources/requirements.txt && \
    /opt/venv/bin/pip install -r mypylib/requirements.txt

VOLUME ["/var/storage"]
ENV STORAGE_LOCATION=/var/storage

ENV PATH="/opt/venv/bin:$PATH"

ENTRYPOINT ["python3", "/usr/src/mytonprovider/mytonprovider.py"]
CMD ["--help"]
