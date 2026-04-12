#!/usr/bin/env bash
#
# MyTonProvider uninstall script.
# Stops services, removes units/binaries/config. With -u USER also
# removes that user's venv and data dir (holds wallet private key).

set -euo pipefail

readonly APP_NAME="mytonprovider"
readonly SERVICE_NAME="mytonproviderd"

readonly SERVICES=(
	"${SERVICE_NAME}"
	"ton-storage"
	"ton-storage-provider"
)

readonly GO_BINARIES=(
	/usr/local/bin/tonutils-storage
	/usr/local/bin/tonutils-storage-provider
)

readonly GO_SOURCES=(
	/usr/src/tonutils-storage
	/usr/src/tonutils-storage-provider
)

readonly GLOBAL_CONFIG_FILE="/var/ton/global.config.json"
readonly GLOBAL_CONFIG_DIR="/var/ton"
readonly SYSTEM_BIN="/usr/local/bin/${APP_NAME}"
readonly TONUTILS_BIN="/usr/local/bin/tonutils"

readonly C_STEP='\033[92m'
readonly C_WARN='\033[93m'
readonly C_ERROR='\033[91m'
readonly C_RESET='\033[0m'

input_user=""
assume_yes=false

die() {
	echo -e "${C_ERROR}${*}${C_RESET}" >&2
	exit 1
}

warn() {
	echo -e "${C_WARN}${*}${C_RESET}"
}

step() {
	local number="$1" total="$2" message="$3"
	echo -e "${C_STEP}[${number}/${total}]${C_RESET} ${message}"
}

show_help() {
	cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -u USER   Also remove user's venv and data dir (holds wallet keys)
  -y        Skip the wallet-keys confirmation prompt
  -h        Show this help

Always removed:
  - systemd units: ${SERVICES[*]}
  - symlinks: ${SYSTEM_BIN}, ${TONUTILS_BIN}
  - Go binaries: ${GO_BINARIES[*]}
  - Go source clones: ${GO_SOURCES[*]}
  - global config: ${GLOBAL_CONFIG_FILE}
  - sudoers fragment: /etc/sudoers.d/${APP_NAME}

NOT removed (shared system state):
  - storage path chosen during init
  - Go toolchain (/usr/local/go)
  - apt packages, deadsnakes PPA
EOF
	exit 0
}

parse_args() {
	if [[ "${1-}" =~ ^-*h(elp)?$ ]]; then
		show_help
	fi
	while getopts "u:yh" flag; do
		case "${flag}" in
			u) input_user="${OPTARG}" ;;
			y) assume_yes=true ;;
			h) show_help ;;
			*) die "Unrecognized flag -${flag}" ;;
		esac
	done
}

ensure_root() {
	if [[ "$(id -u)" != "0" ]]; then
		die "Please run this script as root (sudo)."
	fi
}

confirm_user_data_removal() {
	if [[ "${assume_yes}" == true ]]; then
		return
	fi
	warn "WARNING: the user data dir contains the provider wallet private key."
	echo "Make sure you have backed it up before continuing."
	local answer
	read -r -p "Continue? [y/N] " answer
	case "${answer}" in
		y|Y|yes|YES) ;;
		*) die "Aborted." ;;
	esac
}

stop_services() {
	local svc
	for svc in "${SERVICES[@]}"; do
		systemctl stop "${svc}" 2>/dev/null || true
		systemctl disable "${svc}" 2>/dev/null || true
	done
}

remove_systemd_units() {
	local svc
	for svc in "${SERVICES[@]}"; do
		rm -f "/etc/systemd/system/${svc}.service"
	done
	systemctl daemon-reload || true
}

remove_binaries_and_sources() {
	rm -f "${SYSTEM_BIN}" "${TONUTILS_BIN}"
	rm -f "${GO_BINARIES[@]}"
	rm -rf "${GO_SOURCES[@]}"
}

remove_global_config() {
	rm -f "${GLOBAL_CONFIG_FILE}"
	# Only remove dir if empty (may be shared with other TON tools).
	rmdir "${GLOBAL_CONFIG_DIR}" 2>/dev/null || true
}

remove_sudoers() {
	rm -f "/etc/sudoers.d/${APP_NAME}"
}

remove_user_files() {
	local target="$1" home
	home=$(getent passwd "${target}" | cut -d: -f6)
	if [[ -z "${home}" || ! -d "${home}" ]]; then
		warn "User '${target}' not found — skipping per-user cleanup"
		return
	fi
	rm -rf "${home}/.local/venv/${APP_NAME}"
	rm -rf "${home}/.local/share/${APP_NAME}"
}

main() {
	parse_args "$@"
	ensure_root

	if [[ -n "${input_user}" ]]; then
		confirm_user_data_removal
	fi

	step 1 4 "Stopping and disabling services"
	stop_services

	step 2 4 "Removing systemd units"
	remove_systemd_units

	step 3 4 "Removing binaries, sources, config, sudoers"
	remove_binaries_and_sources
	remove_global_config
	remove_sudoers

	if [[ -n "${input_user}" ]]; then
		step 4 4 "Removing venv and data dir for '${input_user}'"
		remove_user_files "${input_user}"
	else
		step 4 4 "Skipping per-user cleanup (no -u USER)"
	fi

	echo -e "${C_STEP}Uninstall complete.${C_RESET}"
	echo "Note: storage path and its data were NOT removed."
}

main "$@"
