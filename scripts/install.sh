#!/usr/bin/env bash
# Bootstrap installer for mytonprovider.
set -euo pipefail

readonly APP_NAME="mytonprovider"
readonly SRC_DIR="/usr/src"
readonly BIN_DIR="/usr/local/bin"
readonly GLOBAL_CONFIG_PATH="/var/ton/global.config.json"
readonly GLOBAL_CONFIG_URL="https://igroman787.github.io/global.config.json"
readonly APT_BASE_PACKAGES=(git curl wget fio build-essential software-properties-common)
readonly TOTAL_STEPS=8

# ---------- main ----------

main() {
    parse_args "$@"
    header "My TON Provider installer"

    local clone_label="Cloning ${AUTHOR}/${REPO}"
    [[ -n "${REF}" ]] && clone_label="${clone_label}@${REF}"

    step "Installing system packages"        apt_install_base
    step "${clone_label}"                    clone_repository
    step "Downloading TON network config"    install_global_config
    step "Setting up Python environment"     install_python_package
    step "Linking CLI binaries"              install_bin_symlinks
    step "Running install wizard" -i         run_init_wizard
    step "Applying file ownership"           chown_user_data
    step "Waiting for services"  -w          wait_for_services

    footer
}

# ---------- tasks ----------

apt_install_base() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends "${APT_BASE_PACKAGES[@]}"
}

clone_repository() {
    local url="https://github.com/${AUTHOR}/${REPO}.git"
    rm -rf "${SRC_PATH}_tmp"
    if [[ -n "${REF}" ]]; then
        git clone --branch "${REF}" --recursive "${url}" "${SRC_PATH}_tmp"
    else
        git clone --recursive "${url}" "${SRC_PATH}_tmp"
    fi
    rm -rf "${SRC_PATH}"
    mv "${SRC_PATH}_tmp" "${SRC_PATH}"
    chown -R "${USER_NAME}:${USER_NAME}" "${SRC_PATH}"
    git config --system --add safe.directory "${SRC_PATH}" 2>/dev/null || true
}

install_global_config() {
    mkdir -p "$(dirname "${GLOBAL_CONFIG_PATH}")"
    chown "${USER_NAME}:${USER_NAME}" "$(dirname "${GLOBAL_CONFIG_PATH}")"
    if [[ ! -f "${GLOBAL_CONFIG_PATH}" ]]; then
        wget -q "${GLOBAL_CONFIG_URL}" -O "${GLOBAL_CONFIG_PATH}"
    fi
    chown "${USER_NAME}:${USER_NAME}" "${GLOBAL_CONFIG_PATH}"
    chmod 0644 "${GLOBAL_CONFIG_PATH}"
}

install_python_package() {
    local helper="${SRC_PATH}/scripts/install_py_package.sh"
    [[ -x "${helper}" ]] || die "installer helper not found: ${helper}"
    "${helper}" -u "${USER_NAME}" -v "${VENV_PATH}" -p "${SRC_PATH}"
}

install_bin_symlinks() {
    local name target
    for name in "${APP_NAME}" tonutils; do
        target="${VENV_PATH}/bin/${name}"
        [[ -x "${target}" ]] && ln -sf "${target}" "${BIN_DIR}/${name}"
    done
}

run_init_wizard() {
    local venv_bin="${VENV_PATH}/bin/${APP_NAME}"
    [[ -x "${venv_bin}" ]] || die "${APP_NAME} binary not found at ${venv_bin}"
    # SUDO_USER propagation lets ``constants.resolve_install_user`` pick the
    # original user even though the wizard runs as root.
    if [[ -n "${PARAMS_FILE}" ]]; then
        SUDO_USER="${USER_NAME}" "${venv_bin}" install --params "${PARAMS_FILE}"
    else
        SUDO_USER="${USER_NAME}" "${venv_bin}" install
    fi
}

chown_user_data() {
    local work_dir="${USER_HOME}/.local/share/${APP_NAME}"
    [[ -d "${work_dir}" ]] || return 0
    chown -R "${USER_NAME}:${USER_NAME}" "${work_dir}"
}

wait_for_services() {
    local services=(ton-storage ton-storage-provider mytonproviderd)
    local i svc all
    for (( i = 0; i < 30; i++ )); do
        all=1
        for svc in "${services[@]}"; do
            systemctl is-active --quiet "${svc}" || { all=0; break; }
        done
        (( all )) && return 0
        sleep 1
    done
    return 1
}

# ---------- style, args, step runner ----------

readonly C_OK='\033[0;32m'
readonly C_WARN='\033[0;33m'
readonly C_FAIL='\033[0;31m'
readonly C_DIM='\033[0;90m'
readonly C_BOLD='\033[1m'
readonly C_RESET='\033[0m'
readonly LABEL_WIDTH=44

DEBUG=0
STEP_N=0
USER_NAME="${SUDO_USER:-}"
USER_HOME=""
AUTHOR="nessshon"
REPO="mytonprovider"
REF=""
PARAMS_FILE=""
SRC_PATH=""
VENV_PATH=""

show_help() {
    cat <<EOF
Usage: sudo $(basename "$0") [-u USER] [-a AUTHOR] [-r REPO] [-b REF] [-p FILE] [-d]

Options:
  -u USER    Target user (default: \$SUDO_USER)
  -a AUTHOR  GitHub owner (default: nessshon)
  -r REPO    GitHub repository (default: mytonprovider)
  -b REF     Git branch or tag (default: repository default)
  -p FILE    JSON file with install params (non-interactive mode)
  -d         Debug: print each captured command's output
  -h         Show this help and exit
EOF
}

parse_args() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then show_help; exit 0; fi
    [[ "$(id -u)" == "0" ]] || die "must run as root (use sudo)"

    local flag
    while getopts "u:a:r:b:p:dh" flag; do
        case "${flag}" in
            u) USER_NAME="${OPTARG}" ;;
            a) AUTHOR="${OPTARG}" ;;
            r) REPO="${OPTARG}" ;;
            b) REF="${OPTARG}" ;;
            p) PARAMS_FILE="${OPTARG}" ;;
            d) DEBUG=1 ;;
            h) show_help; exit 0 ;;
            *) show_help; exit 1 ;;
        esac
    done

    [[ -n "${USER_NAME}" && "${USER_NAME}" != "root" ]] \
        || die "target user required (-u USER or run via 'sudo' as a non-root user)"
    USER_HOME=$(resolve_user_home "${USER_NAME}")
    [[ -n "${USER_HOME}" ]] || die "user '${USER_NAME}' has no valid home directory"
    if [[ -n "${PARAMS_FILE}" ]]; then
        [[ -f "${PARAMS_FILE}" ]] || die "params file not found: ${PARAMS_FILE}"
        PARAMS_FILE=$(readlink -f "${PARAMS_FILE}")
    fi
    SRC_PATH="${SRC_DIR}/${REPO}"
    VENV_PATH="${USER_HOME}/.local/venv/${APP_NAME}"
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

footer() {
    printf '\n'
    printf '  %bVenv%b    %s\n' "${C_DIM}" "${C_RESET}" "${VENV_PATH}"
    printf '  %bSource%b  %s\n' "${C_DIM}" "${C_RESET}" "${SRC_PATH}"
    printf '  %bRun%b     %s\n' "${C_DIM}" "${C_RESET}" "${APP_NAME}"
    printf '\n'
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

# step "Name" [-i] [-w] cmd args...
#   quiet mode (default): output captured; running line rewritten with result
#   -i: interactive (wizard) — stream output, print separate open/close lines
#   -w: warn-only on non-zero exit
step() {
    local name="$1"; shift
    local interactive=0 warn_only=0
    while [[ "${1:-}" == "-i" || "${1:-}" == "-w" ]]; do
        [[ "$1" == "-i" ]] && interactive=1
        [[ "$1" == "-w" ]] && warn_only=1
        shift
    done

    STEP_N=$(( STEP_N + 1 ))
    local start rc=0
    start=$(_now_ns)

    if (( interactive )); then
        printf '  %b[%d/%d]%b %s\n' "${C_DIM}" "${STEP_N}" "${TOTAL_STEPS}" "${C_RESET}" "${name}"
        "$@" || rc=$?
        if (( rc != 0 )); then
            _line "${C_FAIL}" "fail" "${name}" "$(_elapsed "${start}")" >&2
            exit "${rc}"
        fi
        _line "${C_OK}" "ok" "${name}" "$(_elapsed "${start}")"
        return 0
    fi

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
    elif (( warn_only )); then
        _line "${C_WARN}" "warn" "${name}" "$(_elapsed "${start}")"
        rc=0
    else
        _line "${C_FAIL}" "fail" "${name}" "$(_elapsed "${start}")" >&2
        [[ -n "${log}" && -s "${log}" ]] && { printf '\n' >&2; sed 's/^/    /' "${log}" >&2; }
    fi
    [[ -n "${log}" ]] && rm -f "${log}"
    (( rc == 0 )) || exit "${rc}"
}

main "$@"
