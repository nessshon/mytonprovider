#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'

# Constants
readonly APP_NAME="mytonprovider"
readonly DEFAULT_AUTHOR="nessshon"
readonly DEFAULT_REPO="mytonprovider"
readonly DEFAULT_BRANCH="web"

readonly WORK_DIR="/var/lib/${APP_NAME}"
readonly SRC_BASE="/usr/src"
readonly SRC_DIR="${SRC_BASE}/${APP_NAME}"
readonly VENV_DIR="${WORK_DIR}/venv"
readonly BIN_DIR="/usr/local/bin"

readonly TON_CONFIG_DIR="/var/ton"
readonly TON_CONFIG_PATH="${TON_CONFIG_DIR}/global.config.json"
readonly TON_CONFIG_URL="https://igroman787.github.io/global.config.json"

readonly GO_VERSION="1.24.3"
readonly GO_INSTALL_DIR="/usr/local/go"

# Tonutils repos: always xssnick/<name>; refs overridable via env.
readonly TONUTILS_AUTHOR="xssnick"
readonly TONUTILS_STORAGE_REF="${TONUTILS_STORAGE_REF:-master}"
readonly TONUTILS_STORAGE_PROVIDER_REF="${TONUTILS_STORAGE_PROVIDER_REF:-master}"

readonly APT_PACKAGES=(git curl wget fio build-essential iproute2 iputils-ping python3 python3-venv python3-pip)

readonly TOTAL_STEPS=14

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

export DEBIAN_FRONTEND=noninteractive

# Mutable state
author="${DEFAULT_AUTHOR}"
repo="${DEFAULT_REPO}"
branch="${DEFAULT_BRANCH}"
input_user=""
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
    echo "═══ ${APP_NAME} · install ═══"
    echo
}

build_go_repo() {
    local name="$1"
    local ref="$2"
    local entry="$3"
    local src="${SRC_BASE}/${name}"
    local bin="${BIN_DIR}/${name}"

    step "Building ${TONUTILS_AUTHOR}/${name}@${ref}"
    rm -rf "${src}"
    git clone --quiet --branch "${ref}" \
        "https://github.com/${TONUTILS_AUTHOR}/${name}.git" "${src}"
    (cd "${src}" && go build -o "${bin}" "${entry}")
    [[ -x "${bin}" ]] || die "${name} build failed"
}

show_help() {
    cat <<EOF
Usage: $(basename "$0") [-u USER] [-a AUTHOR] [-r REPO] [-b BRANCH]

Options:
  -u USER     User to own the data dir and run the daemon
              (default: invoking user when escalated via sudo)
  -a AUTHOR   Git repo author (default: ${DEFAULT_AUTHOR})
  -r REPO     Git repo name (default: ${DEFAULT_REPO})
  -b BRANCH   Git branch or tag (default: ${DEFAULT_BRANCH})
  -h          Show this help
EOF
    exit 0
}

# Parse args
while getopts "u:a:r:b:h" flag; do
    case "${flag}" in
        u) input_user="${OPTARG}" ;;
        a) author="${OPTARG}" ;;
        r) repo="${OPTARG}" ;;
        b) branch="${OPTARG}" ;;
        h) show_help ;;
        *) die "Unrecognized flag -${flag}" ;;
    esac
done

# Re-exec as root if needed
if [[ "$(id -u)" != "0" ]]; then
    [[ -z "${input_user}" ]] && input_user="$(whoami)"
    exec sudo -E bash "${0}" -u "${input_user}" -a "${author}" -r "${repo}" -b "${branch}"
fi

[[ -z "${input_user}" && -n "${SUDO_USER:-}" ]] && input_user="${SUDO_USER}"
[[ -n "${input_user}" ]] || die "Pass -u USER, or run via sudo from a non-root user."
id "${input_user}" >/dev/null 2>&1 || die "User '${input_user}' does not exist"

banner

# Install steps
step "Checking system requirements"
command -v apt >/dev/null || die "apt not found — Debian/Ubuntu only"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "Python 3.10+ required (found: $(python3 --version 2>&1))"

step "Installing system packages"
apt update -qq
apt install -y -qq "${APT_PACKAGES[@]}"

step "Installing Go ${GO_VERSION}"
if ! "${GO_INSTALL_DIR}/bin/go" version 2>/dev/null | grep -q "go${GO_VERSION}"; then
    arch="$(dpkg --print-architecture)"
    rm -rf "${GO_INSTALL_DIR}"
    wget -qO- "https://go.dev/dl/go${GO_VERSION}.linux-${arch}.tar.gz" \
        | tar -C "$(dirname "${GO_INSTALL_DIR}")" -xz
fi
ln -sf "${GO_INSTALL_DIR}/bin/go" "${BIN_DIR}/go"
"${GO_INSTALL_DIR}/bin/go" version | grep -q "go${GO_VERSION}" \
    || die "Go ${GO_VERSION} install verification failed"

step "Cloning ${author}/${repo}@${branch}"
mkdir -p "${SRC_BASE}"
rm -rf "${SRC_DIR}"
git clone --quiet --branch "${branch}" --recursive \
    "https://github.com/${author}/${repo}.git" "${SRC_DIR}"

step "Preparing workdir"
mkdir -p "${WORK_DIR}"

step "Creating virtual environment"
rm -rf "${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip

step "Installing ${APP_NAME}"
"${VENV_DIR}/bin/pip" install --quiet "${SRC_DIR}"
ln -sf "${VENV_DIR}/bin/${APP_NAME}" "${BIN_DIR}/${APP_NAME}"
ln -sf "${VENV_DIR}/bin/tonutils" "${BIN_DIR}/tonutils"

step "Downloading global TON config"
mkdir -p "${TON_CONFIG_DIR}"
wget -q -O "${TON_CONFIG_PATH}" "${TON_CONFIG_URL}"

build_go_repo "tonutils-storage" "${TONUTILS_STORAGE_REF}" "cli/main.go"
build_go_repo "tonutils-storage-provider" "${TONUTILS_STORAGE_PROVIDER_REF}" "cmd/main.go"

step "Setting ownership"
chown -R "${input_user}:${input_user}" \
    "${WORK_DIR}" \
    "${SRC_DIR}" \
    "${SRC_BASE}/tonutils-storage" \
    "${SRC_BASE}/tonutils-storage-provider"

git config --system --add safe.directory "${SRC_DIR}"
git config --system --add safe.directory "${SRC_BASE}/tonutils-storage"
git config --system --add safe.directory "${SRC_BASE}/tonutils-storage-provider"

step "Running '${APP_NAME} install'"
"${BIN_DIR}/${APP_NAME}" install

step "Resetting ownership"
chown -R "${input_user}:${input_user}" "${WORK_DIR}"

step "Starting ${APP_NAME}.service"
systemctl start "${APP_NAME}.service"

echo
echo "${C_STEP}✓ ${APP_NAME} installed${C_RESET}"
