#!/bin/bash
# Tear down mytonprovider: stop/remove systemd units, binaries, source dirs, workdir.
# Preserves /var/storage and /var/ton (wallet keys, bag data, network config).

set -euo pipefail

# Paths
readonly APP_NAME="mytonprovider"
readonly WORK_DIR="/var/lib/${APP_NAME}"
readonly SRC_BASE="/usr/src"
readonly BIN_DIR="/usr/local/bin"
readonly SYSTEMD_DIR="/etc/systemd/system"
readonly UV_INSTALL_DIR="/usr/local/uv"
readonly UV_PYTHON_DIR="/usr/local/share/uv-python"

# Inventory (used by stop_services + remove_unit_files)
readonly UNITS=(
    "${APP_NAME}d.service"
    "${APP_NAME}-updater.service"
    "ton-storage.service"
    "ton-storage-provider.service"
)

# Colors
readonly C_STEP=$'\033[92m'
readonly C_ERROR=$'\033[91m'
readonly C_RESET=$'\033[0m'

# Locale (LANG → 2-letter code; falls back to en in t())
_lang="${LANG:-en}"
readonly LOCALE="${_lang:0:2}"

die() {
    echo "${C_ERROR}error:${C_RESET} $*" >&2
    exit 1
}

reexec_as_root() {
    if [[ "$(id -u)" == "0" ]]; then
        return
    fi

    local user user_groups
    user="$(whoami)"
    user_groups="$(groups "${user}")"

    local args=(bash "$0" "$@")
    if [[ "${user_groups}" == *"sudo"* ]]; then
        exec sudo "${args[@]}"
    else
        exec su -c "$(printf '%q ' "${args[@]}")"
    fi
}

stop_services() {
    local unit
    for unit in "${UNITS[@]}"; do
        systemctl stop "${unit}" 2>/dev/null || true
        systemctl disable "${unit}" 2>/dev/null || true
    done
}

remove_unit_files() {
    local unit
    for unit in "${UNITS[@]}"; do
        rm -f "${SYSTEMD_DIR}/${unit}"
    done
    systemctl daemon-reload
}

remove_binaries() {
    rm -rf \
        "${BIN_DIR}/${APP_NAME}" \
        "${BIN_DIR}/tonutils" \
        "${BIN_DIR}/tonutils-storage" \
        "${BIN_DIR}/tonutils-storage-provider"
}

remove_source_dirs() {
    rm -rf \
        "${SRC_BASE}/${APP_NAME}" \
        "${SRC_BASE}/tonutils-storage" \
        "${SRC_BASE}/tonutils-storage-provider"
}

remove_uv() {
    rm -rf "${UV_INSTALL_DIR}" "${UV_PYTHON_DIR}"
}

remove_workdir() {
    rm -rf "${WORK_DIR}"
}

t() {
    case "${LOCALE}:$1" in
        ru:header) echo "${APP_NAME} · удаление" ;;
        zh:header) echo "${APP_NAME} · 卸载" ;;
        *:header)  echo "${APP_NAME} · uninstall" ;;

        ru:stop) echo "Остановка и отключение служб" ;;
        zh:stop) echo "停止并禁用服务" ;;
        *:stop)  echo "Stopping and disabling services" ;;

        ru:units) echo "Удаление systemd unit-файлов" ;;
        zh:units) echo "删除 systemd unit 文件" ;;
        *:units)  echo "Removing systemd unit files" ;;

        ru:bins) echo "Удаление бинарей и симлинков" ;;
        zh:bins) echo "删除二进制文件和符号链接" ;;
        *:bins)  echo "Removing binaries and symlinks" ;;

        ru:src) echo "Удаление исходников" ;;
        zh:src) echo "删除源码目录" ;;
        *:src)  echo "Removing source dirs" ;;

        ru:uv) echo "Удаление uv toolchain" ;;
        zh:uv) echo "删除 uv toolchain" ;;
        *:uv)  echo "Removing uv toolchain" ;;

        ru:wd) echo "Удаление рабочей директории" ;;
        zh:wd) echo "删除工作目录" ;;
        *:wd)  echo "Removing workdir" ;;

        ru:done) echo "✓ ${APP_NAME} удалён" ;;
        zh:done) echo "✓ ${APP_NAME} 已卸载" ;;
        *:done)  echo "✓ ${APP_NAME} uninstalled" ;;
    esac
}

mytonprovider_teardown() {
    echo
    echo "═══ $(t header) ═══"
    echo

    echo "${C_STEP}[1/6]${C_RESET} $(t stop)"
    stop_services

    echo "${C_STEP}[2/6]${C_RESET} $(t units)"
    remove_unit_files

    echo "${C_STEP}[3/6]${C_RESET} $(t bins)"
    remove_binaries

    echo "${C_STEP}[4/6]${C_RESET} $(t src)"
    remove_source_dirs

    echo "${C_STEP}[5/6]${C_RESET} $(t uv)"
    remove_uv

    echo "${C_STEP}[6/6]${C_RESET} $(t wd)"
    remove_workdir

    echo
    echo "${C_STEP}$(t done)${C_RESET}"
}

reexec_as_root "$@"
mytonprovider_teardown
