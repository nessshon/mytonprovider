#!/usr/bin/env bash

set -euo pipefail

IFS=$'\n\t'

readonly INSTALL_MARKER=/var/lib/mytonprovider/.installed

readonly REQUIRED_VARS=(
    MTP_TON_STORAGE_PROVIDER_STORAGE_COST
    MTP_TON_STORAGE_PROVIDER_SPACE_GB
)

if [[ ! -f "${INSTALL_MARKER}" ]]; then
    for var in "${REQUIRED_VARS[@]}"; do
        [[ -n "${!var:-}" ]] || { echo "error: ${var} required - set in .env" >&2; exit 1; }
    done
    echo ">>> First-run setup: mytonprovider install"
    mytonprovider install
    touch "${INSTALL_MARKER}"
fi

exec /usr/local/bin/systemctl
