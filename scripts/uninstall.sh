#!/usr/bin/env bash
# Remove mytonprovider systemd units, binaries, source clones and TON global
# config. With -u USER also removes the user's venv and data (contains the
# provider wallet private key).
set -euo pipefail

readonly APP_NAME="mytonprovider"
readonly SRC_DIR="/usr/src"
readonly BIN_DIR="/usr/local/bin"
readonly SYSTEMD_DIR="/etc/systemd/system"
readonly GLOBAL_CONFIG_PATH="/var/ton/global.config.json"

readonly SERVICES=(
    mytonproviderd
    mytonprovider-update.timer
    mytonprovider-update.service
    ton-storage
    ton-storage-provider
)
readonly SOURCE_CLONES=(mytonprovider tonutils-storage tonutils-storage-provider)
readonly BIN_FILES=(
    "${BIN_DIR}/${APP_NAME}"
    "${BIN_DIR}/tonutils"
    "${BIN_DIR}/tonutils-storage"
    "${BIN_DIR}/tonutils-storage-provider"
)

# ---------- main ----------

main() {
    parse_args "$@"
    [[ -n "${USER_NAME}" ]] && confirm_user_data_removal
    TOTAL_STEPS=$(( 4 + (${#USER_NAME} > 0 ? 1 : 0) ))
    header "My TON Provider uninstaller"

    step "Stopping systemd services"         remove_services
    step "Removing source clones"            remove_sources
    step "Removing CLI binaries"             remove_binaries
    step "Removing TON network config"       remove_global_config
    [[ -n "${USER_NAME}" ]] && \
        step "Removing user data (${USER_NAME})" remove_user_data

    printf '\n'
}

# ---------- tasks ----------

remove_services() {
    local svc unit
    for svc in "${SERVICES[@]}"; do
        systemctl stop "${svc}" 2>/dev/null || true
        systemctl disable "${svc}" 2>/dev/null || true
        unit="${SYSTEMD_DIR}/${svc}"
        [[ "${unit}" == *.service || "${unit}" == *.timer ]] || unit="${unit}.service"
        rm -f "${unit}"
    done
    systemctl daemon-reload
}

remove_sources() {
    local name
    for name in "${SOURCE_CLONES[@]}"; do
        rm -rf "${SRC_DIR}/${name}"
    done
}

remove_binaries() {
    local path
    for path in "${BIN_FILES[@]}"; do
        rm -f "${path}"
    done
}

remove_global_config() {
    rm -f "${GLOBAL_CONFIG_PATH}"
    rmdir "$(dirname "${GLOBAL_CONFIG_PATH}")" 2>/dev/null || true
}

remove_user_data() {
    local home
    home=$(resolve_user_home "${USER_NAME}")
    [[ -n "${home}" ]] || die "user '${USER_NAME}' not found"
    rm -rf "${home}/.local/venv/${APP_NAME}"
    rm -rf "${home}/.local/share/${APP_NAME}"
    rm -rf "${home}/.cache/pip"
}

# ---------- style, args, step runner ----------

readonly C_OK='\033[0;32m'
readonly C_WARN='\033[0;33m'
readonly C_FAIL='\033[0;31m'
readonly C_DIM='\033[0;90m'
readonly C_BOLD='\033[1m'
readonly C_RESET='\033[0m'
readonly LABEL_WIDTH=40

DEBUG=0
STEP_N=0
TOTAL_STEPS=0
USER_NAME=""
ASSUME_YES=0

show_help() {
    cat <<EOF
Usage: sudo $(basename "$0") [-u USER] [-y] [-d]

Options:
  -u USER   Also remove ~USER/.local/venv/mytonprovider and
            ~USER/.local/share/mytonprovider (needs confirmation)
  -y        Skip confirmation prompt for user data removal
  -d        Debug: print each captured command's output
  -h        Show this help and exit
EOF
}

parse_args() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then show_help; exit 0; fi
    [[ "$(id -u)" == "0" ]] || die "must run as root (use sudo)"
    local flag
    while getopts "u:ydh" flag; do
        case "${flag}" in
            u) USER_NAME="${OPTARG}" ;;
            y) ASSUME_YES=1 ;;
            d) DEBUG=1 ;;
            h) show_help; exit 0 ;;
            *) show_help; exit 1 ;;
        esac
    done
}

confirm_user_data_removal() {
    (( ASSUME_YES )) && return 0
    printf '  %bwarning:%b user data contains the provider wallet key\n' \
        "${C_WARN}" "${C_RESET}" >&2
    read -r -p "  Proceed? [y/N] " answer
    [[ "${answer}" =~ ^[Yy]$ ]] || die "aborted"
}

resolve_user_home() {
    local user="$1" home
    home=$(getent passwd "${user}" | cut -d: -f6 || true)
    [[ -n "${home}" && -d "${home}" ]] && printf '%s\n' "${home}"
}

die() {
    printf '%b%s%b %s\n' "${C_FAIL}" "error:" "${C_RESET}" "$*" >&2
    exit 1
}

header() {
    printf '\n  %b%s%b\n\n' "${C_BOLD}" "$1" "${C_RESET}"
}

_now_ns() {
    date +%s%N 2>/dev/null || printf '%d000000000\n' "$(date +%s)"
}

_elapsed() {
    local ms=$(( ( $(_now_ns) - $1 ) / 1000000 ))
    if   (( ms < 1000 ));  then printf '%dms' "${ms}"
    elif (( ms < 60000 )); then printf '%d.%ds' "$(( ms / 1000 ))" "$(( ms % 1000 / 100 ))"
    else printf '%dm%ds' "$(( ms / 60000 ))" "$(( ms % 60000 / 1000 ))"
    fi
}

_line() {
    local color="$1" label="$2" name="$3" elapsed="$4"
    printf '  %b[%d/%d]%b %-*s  %b%-4s%b %b%s%b\n' \
        "${C_DIM}" "${STEP_N}" "${TOTAL_STEPS}" "${C_RESET}" \
        "${LABEL_WIDTH}" "${name}" \
        "${color}" "${label}" "${C_RESET}" \
        "${C_DIM}" "${elapsed}" "${C_RESET}"
}

step() {
    local name="$1"; shift
    STEP_N=$(( STEP_N + 1 ))
    local start rc=0
    start=$(_now_ns)
    local log=""

    printf '  %b[%d/%d]%b %s ...' "${C_DIM}" "${STEP_N}" "${TOTAL_STEPS}" "${C_RESET}" "${name}"
    if (( DEBUG )); then
        printf '\n'
        "$@" || rc=$?
    else
        log=$(mktemp)
        "$@" >"${log}" 2>&1 || rc=$?
        printf '\r\033[K'
    fi

    if (( rc == 0 )); then
        _line "${C_OK}" "ok" "${name}" "$(_elapsed "${start}")"
    else
        _line "${C_FAIL}" "fail" "${name}" "$(_elapsed "${start}")" >&2
        [[ -n "${log}" && -s "${log}" ]] && { printf '\n' >&2; sed 's/^/    /' "${log}" >&2; }
    fi
    [[ -n "${log}" ]] && rm -f "${log}"
    (( rc == 0 )) || exit "${rc}"
}

main "$@"
