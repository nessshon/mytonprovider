#!/bin/bash
# Install mytonprovider as a systemd service with the TON storage provider stack.
# Run from a non-root user (escalates via sudo or su) or pass -u USER from root.

set -euo pipefail

# Defaults
readonly APP_NAME="mytonprovider"
readonly DEFAULT_AUTHOR="nessshon"
readonly DEFAULT_REPO="mytonprovider"
readonly DEFAULT_BRANCH="master"

# Paths
readonly WORK_DIR="/var/lib/${APP_NAME}"
readonly SRC_BASE="/usr/src"
readonly SRC_DIR="${SRC_BASE}/${APP_NAME}"
readonly VENV_DIR="${WORK_DIR}/venv"
readonly BIN_DIR="/usr/local/bin"

# TON config
readonly TON_CONFIG_DIR="/var/ton"
readonly TON_CONFIG_PATH="${TON_CONFIG_DIR}/global.config.json"
readonly TON_CONFIG_URL="https://igroman787.github.io/global.config.json"

# Go toolchain
readonly GO_VERSION="1.24.3"
readonly GO_INSTALL_DIR="/usr/local/go"

# Python toolchain
readonly PYTHON_VERSION="3.12"
readonly UV_VERSION="0.11.14"
readonly UV_INSTALL_DIR="/usr/local/uv"
readonly UV_PYTHON_DIR="/usr/local/share/uv-python"
# Shared path so install_user (running the daemon) can read the Python distribution.
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_DIR}"

# Required apt packages
readonly APT_PACKAGES=(
    git
    curl
    wget
    fio
    build-essential
    iproute2
    iputils-ping
)

# Colors
readonly C_STEP=$'\033[92m'
readonly C_ERROR=$'\033[91m'
readonly C_RESET=$'\033[0m'

# Locale (LANG → 2-letter code; falls back to en in t())
_lang="${LANG:-en}"
readonly LOCALE="${_lang:0:2}"

# Default args
author="${DEFAULT_AUTHOR}"
repo="${DEFAULT_REPO}"
branch="${DEFAULT_BRANCH}"
install_user=""

die() {
    echo "${C_ERROR}error:${C_RESET} $*" >&2
    exit 1
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

parse_args() {
    while getopts "u:a:r:b:h" flag; do
        case "${flag}" in
            u) install_user="${OPTARG}" ;;
            a) author="${OPTARG}" ;;
            r) repo="${OPTARG}" ;;
            b) branch="${OPTARG}" ;;
            h) show_help ;;
            *) die "Unrecognized flag -${flag}" ;;
        esac
    done
}

reexec_as_root() {
    if [[ "$(id -u)" == "0" ]]; then
        return
    fi

    local user user_groups
    user="$(whoami)"
    user_groups="$(groups "${user}")"

    if [[ -z "${install_user}" ]]; then
        install_user="${user}"
    fi

    local args=(bash "$0" -u "${install_user}" -a "${author}" -r "${repo}" -b "${branch}")
    if [[ "${user_groups}" == *"sudo"* ]]; then
        exec sudo "${args[@]}"
    else
        exec su -c "$(printf '%q ' "${args[@]}")"
    fi
}

set_install_user() {
    if [[ -z "${install_user}" ]] && [[ -n "${SUDO_USER:-}" ]]; then
        install_user="${SUDO_USER}"
    fi
    if [[ -z "${install_user}" ]]; then
        install_user="$(whoami)"
    fi
    if ! id "${install_user}" >/dev/null 2>&1; then
        die "User '${install_user}' does not exist"
    fi
}

install_apt_packages() {
    if ! command -v apt >/dev/null; then
        die "apt not found — Debian/Ubuntu only"
    fi
    apt update -qq
    apt install -y -qq "${APT_PACKAGES[@]}"
}

install_uv() {
    if ! "${UV_INSTALL_DIR}/uv" --version 2>/dev/null | grep -q "uv ${UV_VERSION}"; then
        local arch_dpkg arch_uv
        arch_dpkg="$(dpkg --print-architecture)"
        case "${arch_dpkg}" in
            amd64) arch_uv="x86_64-unknown-linux-musl" ;;
            arm64) arch_uv="aarch64-unknown-linux-musl" ;;
            *) die "Unsupported architecture: ${arch_dpkg}" ;;
        esac
        rm -rf "${UV_INSTALL_DIR}"
        mkdir -p "${UV_INSTALL_DIR}"
        wget --tries=3 --timeout=30 -qO- \
            "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${arch_uv}.tar.gz" \
            | tar -xz -C "${UV_INSTALL_DIR}" --strip-components=1
    fi
}

install_go() {
    if ! "${GO_INSTALL_DIR}/bin/go" version 2>/dev/null | grep -q "go${GO_VERSION}"; then
        local arch
        arch="$(dpkg --print-architecture)"
        rm -rf "${GO_INSTALL_DIR}"
        wget --tries=3 --timeout=30 -qO- "https://go.dev/dl/go${GO_VERSION}.linux-${arch}.tar.gz" \
            | tar -C "$(dirname "${GO_INSTALL_DIR}")" -xz
    fi
    ln -sf "${GO_INSTALL_DIR}/bin/go" "${BIN_DIR}/go"
}

clone_sources() {
    mkdir -p "${SRC_BASE}"
    rm -rf "${SRC_DIR}"
    git clone \
        --quiet \
        --branch "${branch}" \
        --recursive \
        "https://github.com/${author}/${repo}.git" \
        "${SRC_DIR}"
    chown -R "${install_user}:${install_user}" "${SRC_DIR}"
    if ! git config --system --get-all safe.directory 2>/dev/null | grep -qxF "${SRC_DIR}"; then
        git config --system --add safe.directory "${SRC_DIR}"
    fi
}

create_venv() {
    rm -rf "${VENV_DIR}"
    "${UV_INSTALL_DIR}/uv" venv --quiet --seed --python "${PYTHON_VERSION}" "${VENV_DIR}"
}

install_app() {
    "${UV_INSTALL_DIR}/uv" pip install --quiet --python "${VENV_DIR}/bin/python" "${SRC_DIR}"
    rm -rf "${BIN_DIR}/${APP_NAME}" "${BIN_DIR}/tonutils"
    ln -s "${VENV_DIR}/bin/${APP_NAME}" "${BIN_DIR}/${APP_NAME}"
    ln -s "${VENV_DIR}/bin/tonutils" "${BIN_DIR}/tonutils"
}

download_ton_config() {
    mkdir -p "${TON_CONFIG_DIR}"
    wget --tries=3 --timeout=30 -q -O "${TON_CONFIG_PATH}" "${TON_CONFIG_URL}"
}

run_app_install() {
    chown -R "${install_user}:${install_user}" "${WORK_DIR}"
    "${BIN_DIR}/${APP_NAME}" install
    chown -R "${install_user}:${install_user}" "${WORK_DIR}"
}

start_service() {
    systemctl restart "${APP_NAME}d.service"
}

t() {
    case "${LOCALE}:$1" in
        ru:header) echo "${APP_NAME} · установка" ;;
        zh:header) echo "${APP_NAME} · 安装" ;;
        *:header)  echo "${APP_NAME} · install" ;;

        ru:apt) echo "Установка системных пакетов" ;;
        zh:apt) echo "安装系统包" ;;
        *:apt)  echo "Installing system packages" ;;

        ru:uv) echo "Установка uv ${UV_VERSION}" ;;
        zh:uv) echo "安装 uv ${UV_VERSION}" ;;
        *:uv)  echo "Installing uv ${UV_VERSION}" ;;

        ru:go) echo "Установка Go ${GO_VERSION}" ;;
        zh:go) echo "安装 Go ${GO_VERSION}" ;;
        *:go)  echo "Installing Go ${GO_VERSION}" ;;

        ru:clone) echo "Клонирование ${author}/${repo}@${branch}" ;;
        zh:clone) echo "克隆 ${author}/${repo}@${branch}" ;;
        *:clone)  echo "Cloning ${author}/${repo}@${branch}" ;;

        ru:venv) echo "Создание виртуального окружения (Python ${PYTHON_VERSION})" ;;
        zh:venv) echo "创建虚拟环境 (Python ${PYTHON_VERSION})" ;;
        *:venv)  echo "Creating virtual environment (Python ${PYTHON_VERSION})" ;;

        ru:app) echo "Установка ${APP_NAME}" ;;
        zh:app) echo "安装 ${APP_NAME}" ;;
        *:app)  echo "Installing ${APP_NAME}" ;;

        ru:cfg) echo "Скачивание глобального TON config" ;;
        zh:cfg) echo "下载全局 TON config" ;;
        *:cfg)  echo "Downloading global TON config" ;;

        ru:run) echo "Запуск '${APP_NAME} install'" ;;
        zh:run) echo "运行 '${APP_NAME} install'" ;;
        *:run)  echo "Running '${APP_NAME} install'" ;;

        ru:svc) echo "Запуск ${APP_NAME}d.service" ;;
        zh:svc) echo "启动 ${APP_NAME}d.service" ;;
        *:svc)  echo "Starting ${APP_NAME}d.service" ;;

        ru:done) echo "✓ ${APP_NAME} установлен" ;;
        zh:done) echo "✓ ${APP_NAME} 已安装" ;;
        *:done)  echo "✓ ${APP_NAME} installed" ;;
    esac
}

mytonprovider_setup() {
    echo
    echo "═══ $(t header) ═══"
    echo

    echo "${C_STEP}[1/9]${C_RESET} $(t apt)"
    install_apt_packages

    echo "${C_STEP}[2/9]${C_RESET} $(t uv)"
    install_uv

    echo "${C_STEP}[3/9]${C_RESET} $(t go)"
    install_go

    echo "${C_STEP}[4/9]${C_RESET} $(t clone)"
    clone_sources

    echo "${C_STEP}[5/9]${C_RESET} $(t venv)"
    create_venv

    echo "${C_STEP}[6/9]${C_RESET} $(t app)"
    install_app

    echo "${C_STEP}[7/9]${C_RESET} $(t cfg)"
    download_ton_config

    echo "${C_STEP}[8/9]${C_RESET} $(t run)"
    run_app_install

    echo "${C_STEP}[9/9]${C_RESET} $(t svc)"
    start_service

    echo
    echo "${C_STEP}$(t done)${C_RESET}"
}

parse_args "$@"
reexec_as_root
set_install_user
mytonprovider_setup
