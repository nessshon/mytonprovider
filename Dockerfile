FROM python:3.12-slim-bookworm

# Build args
ARG GO_VERSION=1.24.3
ARG TON_CONFIG_URL=https://igroman787.github.io/global.config.json
ARG SYSTEMCTL_REPLACEMENT_VERSION=v1.7.1097
ARG TONUTILS_STORAGE_REF=master
ARG TONUTILS_STORAGE_PROVIDER_REF=master
ARG MYTONPROVIDER_REF=master

# OCI labels
LABEL org.opencontainers.image.source="https://github.com/nessshon/mytonprovider"
LABEL org.opencontainers.image.description="TON storage provider manager."
LABEL org.opencontainers.image.licenses="GPL-3.0-or-later"

# Runtime environment
ENV PATH=/usr/local/go/bin:/opt/mytonprovider-venv/bin:${PATH}
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Container-side path for ton-storage data
ENV MTP_TON_STORAGE_PATH=/var/storage

# System packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git fio build-essential \
        iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Go toolchain
RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${arch}.tar.gz" \
        | tar -C /usr/local -xz \
    && /usr/local/go/bin/go version

# Tonutils Go binaries
RUN git clone --branch "${TONUTILS_STORAGE_REF}" \
        https://github.com/xssnick/tonutils-storage.git /usr/src/tonutils-storage \
    && go -C /usr/src/tonutils-storage build -o /usr/local/bin/tonutils-storage cli/main.go
RUN git clone --branch "${TONUTILS_STORAGE_PROVIDER_REF}" \
        https://github.com/xssnick/tonutils-storage-provider.git /usr/src/tonutils-storage-provider \
    && go -C /usr/src/tonutils-storage-provider build -o /usr/local/bin/tonutils-storage-provider cmd/main.go

# systemd replacement
RUN curl -fsSL "https://github.com/gdraheim/docker-systemctl-replacement/raw/${SYSTEMCTL_REPLACEMENT_VERSION}/files/docker/systemctl3.py" \
        -o /usr/local/bin/systemctl \
    && curl -fsSL "https://github.com/gdraheim/docker-systemctl-replacement/raw/${SYSTEMCTL_REPLACEMENT_VERSION}/files/docker/journalctl3.py" \
        -o /usr/local/bin/journalctl \
    && chmod +x /usr/local/bin/systemctl /usr/local/bin/journalctl

# TON global network config
RUN mkdir -p /var/ton \
    && curl -fsSL "${TON_CONFIG_URL}" -o /var/ton/global.config.json

# Python virtual environment
RUN python3 -m venv /opt/mytonprovider-venv \
    && pip install --no-cache-dir --upgrade pip \
    && mkdir -p /var/lib/mytonprovider \
    && ln -s /opt/mytonprovider-venv /var/lib/mytonprovider/venv

# mytonprovider package
RUN git clone --branch "${MYTONPROVIDER_REF}" \
        https://github.com/nessshon/mytonprovider.git /usr/src/mytonprovider
WORKDIR /usr/src/mytonprovider
RUN pip install --no-cache-dir . \
    && ln -sf /opt/mytonprovider-venv/bin/mytonprovider /usr/local/bin/mytonprovider \
    && ln -sf /opt/mytonprovider-venv/bin/tonutils /usr/local/bin/tonutils

# Entrypoint: first-run install, then handoff to systemctl PID 1
COPY --chmod=0755 <<'EOF' /usr/local/bin/entrypoint.sh
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

readonly INSTALL_MARKER=/var/lib/mytonprovider/.installed

if [[ ! -f "${INSTALL_MARKER}" ]]; then
    echo ">>> First-run setup: mytonprovider install"
    mytonprovider install
    touch "${INSTALL_MARKER}"
fi

exec /usr/local/bin/systemctl
EOF

VOLUME ["/var/lib/mytonprovider", "/etc/systemd/system", "/var/storage"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
