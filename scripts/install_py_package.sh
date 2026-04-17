#!/usr/bin/env bash
# Install or upgrade a Python package into a user's venv.
# Creates the venv on first run, installing Python 3.10+ from the deadsnakes
# PPA when none is available. Optionally restarts a systemd service.
set -euo pipefail

readonly PY_MAJOR=3
readonly PY_MINOR=10

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

show_help() {
    cat <<EOF
Usage: $(basename "$0") -u USER -v VENV -p PATH [-s SERVICE]

  -u USER     User whose venv receives the install
  -v VENV     Absolute path to the venv directory
  -p PATH     Local package source (must contain pyproject.toml)
  -s SERVICE  Optional systemd service to restart after install
  -h          Show this help and exit
EOF
}

# ---- tasks ----

# Pick an existing Python 3.10+ binary, or install 3.11 from deadsnakes.
detect_or_install_python() {
    local candidate
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "${candidate}" >/dev/null 2>&1 || continue
        "${candidate}" -c "import sys; sys.exit(0 if sys.version_info >= (${PY_MAJOR}, ${PY_MINOR}) else 1)" \
            2>/dev/null || continue
        printf '%s\n' "${candidate}"
        return 0
    done
    export DEBIAN_FRONTEND=noninteractive
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-dev
    printf 'python3.11\n'
}

# Install the venv apt package matching the chosen interpreter.
install_venv_package() {
    local pkg="python3-venv"
    [[ "$1" == python3.* ]] && pkg="$1-venv"
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y --no-install-recommends "${pkg}"
}

# Create a fresh venv owned by ${user} and bootstrap pip.
create_venv() {
    local py parent
    py=$(detect_or_install_python)
    install_venv_package "${py}"
    parent=$(dirname "${VENV_PATH}")
    mkdir -p "${parent}"
    chown "${user}:${user}" "${parent}"
    rm -rf "${VENV_PATH}"
    sudo -u "${user}" "${py}" -m venv "${VENV_PATH}"
    sudo -u "${user}" "${VENV_PATH}/bin/pip" install --upgrade --no-cache-dir pip
}

# --force-reinstall + --no-cache-dir guarantee git-pinned deps (e.g.
# mypycli@vX.Y.Z) refetch the current tag instead of reusing a stale wheel.
pip_install() {
    sudo -u "${user}" "${VENV_PATH}/bin/pip" install \
        --upgrade --force-reinstall --no-cache-dir "${src_path}"
}

service_restart() {
    [[ -n "${service_name}" ]] || return 0
    systemctl cat "${service_name}" >/dev/null 2>&1 || return 0
    systemctl restart "${service_name}"
}

main() {
    [[ -x "${VENV_PATH}/bin/pip" ]] || create_venv
    pip_install
    service_restart
}

# ---- arg parsing ----

user=""
venv_path=""
src_path=""
service_name=""

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then show_help; exit 0; fi
[[ "$(id -u)" == "0" ]] || die "must run as root"

while getopts "u:v:p:s:h" flag; do
    case "${flag}" in
        u) user="${OPTARG}" ;;
        v) venv_path="${OPTARG}" ;;
        p) src_path="${OPTARG}" ;;
        s) service_name="${OPTARG}" ;;
        h) show_help; exit 0 ;;
        *) show_help; exit 1 ;;
    esac
done

[[ -n "${user}" ]]                     || die "user (-u) is required"
id -u "${user}" >/dev/null 2>&1        || die "user '${user}' does not exist"
[[ -n "${venv_path}" ]]                || die "venv path (-v) is required"
[[ "${venv_path}" = /* ]]              || die "venv path must be absolute: ${venv_path}"
[[ -n "${src_path}" ]]                 || die "source path (-p) is required"
[[ -d "${src_path}" ]]                 || die "source path not found: ${src_path}"
[[ -f "${src_path}/pyproject.toml" ]]  || die "no pyproject.toml at ${src_path}"

readonly VENV_PATH="${venv_path}"

main
