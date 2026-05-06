#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'

# Constants
readonly APP_NAME="mytonprovider"
readonly WORK_DIR="/var/lib/${APP_NAME}"
readonly SRC_BASE="/usr/src"
readonly BIN_DIR="/usr/local/bin"
readonly SYSTEMD_DIR="/etc/systemd/system"

readonly UNITS=(
    "${APP_NAME}.service"
    "${APP_NAME}-updater.service"
    "ton-storage.service"
    "ton-storage-provider.service"
)

readonly BINARIES=(
    "${APP_NAME}"
    "tonutils"
    "tonutils-storage"
    "tonutils-storage-provider"
)

readonly SRC_REPOS=(
    "${APP_NAME}"
    "tonutils-storage"
    "tonutils-storage-provider"
)

readonly TOTAL_STEPS=5

# Color codes (TTY only)
if [[ -t 1 ]]; then
    readonly C_STEP=$'\033[92m'
    readonly C_ERROR=$'\033[91m'
    readonly C_RESET=$'\033[0m'
else
    readonly C_STEP=''
    readonly C_ERROR=''
    readonly C_RESET=''
fi

# Mutable state
current_step=0

# Helpers
die() {
    echo "${C_ERROR}error:${C_RESET} $*" >&2
    exit 1
}

step() {
    current_step=$((current_step + 1))
    echo "${C_STEP}[${current_step}/${TOTAL_STEPS}]${C_RESET} $*"
}

banner() {
    echo
    echo "═══ ${APP_NAME} · uninstall ═══"
    echo
}

# Re-exec as root if needed
if [[ "$(id -u)" != "0" ]]; then
    exec sudo -E bash "${0}" "$@"
fi

banner

# Uninstall steps
step "Stopping and disabling services"
for unit in "${UNITS[@]}"; do
    systemctl stop "${unit}" 2>/dev/null || true
    systemctl disable "${unit}" 2>/dev/null || true
done

step "Removing systemd unit files"
for unit in "${UNITS[@]}"; do
    rm -f "${SYSTEMD_DIR}/${unit}"
done
systemctl daemon-reload

step "Removing binaries and symlinks"
for bin in "${BINARIES[@]}"; do
    rm -f "${BIN_DIR}/${bin}"
done

step "Removing source dirs"
for repo in "${SRC_REPOS[@]}"; do
    rm -rf "${SRC_BASE}/${repo}"
done

step "Removing workdir"
rm -rf "${WORK_DIR}"

echo
echo "${C_STEP}✓ ${APP_NAME} uninstalled${C_RESET}"
