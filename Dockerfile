FROM python:3.12-slim-bookworm
# Container image for mytonprovider with the TON storage provider stack.
# Uses a fake systemctl as PID 1 to run service units without a real init.

ARG GO_VERSION=1.24.3
ARG SYSTEMCTL_REPLACEMENT_VERSION=v1.7.1097
ARG TON_CONFIG_URL=https://igroman787.github.io/global.config.json

LABEL org.opencontainers.image.source="https://github.com/nessshon/mytonprovider" \
      org.opencontainers.image.description="TON storage provider manager." \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENV PATH=/usr/local/go/bin:/opt/mytonprovider-venv/bin:${PATH} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MTP_TON_STORAGE_PATH=/var/storage

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git fio build-essential iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*

RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${arch}.tar.gz" | tar -C /usr/local -xz

# Fake systemctl is PID 1 - manages service units in the absence of a real init.
RUN curl -fsSL "https://github.com/gdraheim/docker-systemctl-replacement/raw/${SYSTEMCTL_REPLACEMENT_VERSION}/files/docker/systemctl3.py" \
        -o /usr/local/bin/systemctl \
    && curl -fsSL "https://github.com/gdraheim/docker-systemctl-replacement/raw/${SYSTEMCTL_REPLACEMENT_VERSION}/files/docker/journalctl3.py" \
        -o /usr/local/bin/journalctl \
    && chmod +x /usr/local/bin/systemctl /usr/local/bin/journalctl

RUN mkdir -p /var/ton /var/lib/mytonprovider \
    && curl -fsSL "${TON_CONFIG_URL}" -o /var/ton/global.config.json \
    && python3 -m venv /opt/mytonprovider-venv \
    && pip install --no-cache-dir --upgrade pip \
    && ln -s /opt/mytonprovider-venv /var/lib/mytonprovider/venv

COPY . /usr/src/mytonprovider
RUN pip install --no-cache-dir /usr/src/mytonprovider \
    && ln -sf /opt/mytonprovider-venv/bin/mytonprovider /usr/local/bin/mytonprovider \
    && ln -sf /opt/mytonprovider-venv/bin/tonutils /usr/local/bin/tonutils

# First-run install + handoff to systemctl PID 1.
COPY --chmod=0755 scripts/entrypoint.sh /usr/local/bin/entrypoint.sh

VOLUME ["/etc/systemd/system", "/usr/local/bin", "/usr/src", "/var/lib/mytonprovider", "/var/storage"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
