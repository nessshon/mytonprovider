#!/usr/bin/env bash
#
# MyTonProvider install script.
# Installs deps, creates venv, pip-installs from git, runs init wizard.

set -euo pipefail

# Canonical package name (matches pyproject.toml entry-point).
readonly APP_NAME="mytonprovider"

readonly DEFAULT_AUTHOR="nessshon"
readonly DEFAULT_REPO="mytonprovider"
readonly DEFAULT_BRANCH="v1.0.0"

# Suppress interactive apt prompts (tzdata etc.).
export DEBIAN_FRONTEND=noninteractive

readonly REQUIRED_PYTHON_MAJOR=3
readonly REQUIRED_PYTHON_MINOR=10

# Python venv package is handled separately (may need deadsnakes PPA).
readonly APT_BASE_PACKAGES=(
	git
	curl
	wget
	fio
	build-essential
	software-properties-common
)

# Installed from deadsnakes if system python is too old.
readonly FALLBACK_PYTHON="python3.11"

readonly C_STEP='\033[92m'
readonly C_ERROR='\033[91m'
readonly C_RESET='\033[0m'

author="${DEFAULT_AUTHOR}"
repo="${DEFAULT_REPO}"
branch="${DEFAULT_BRANCH}"
input_user=""
python_bin=""
init_args=()

die() {
	echo -e "${C_ERROR}${*}${C_RESET}" >&2
	exit 1
}

step_start() {
	echo -n -e "${C_STEP}${1}${C_RESET}... "
}

step_done() {
	if [[ -n "${1-}" ]]; then
		echo -e "${C_STEP}done${C_RESET} (${1})"
	else
		echo -e "${C_STEP}done${C_RESET}"
	fi
}

# Run a command silently; on failure dump captured output and exit.
run_quiet() {
	local log
	log=$(mktemp)
	if "$@" > "${log}" 2>&1; then
		rm -f "${log}"
	else
		echo -e "${C_ERROR}Command failed: $*${C_RESET}" >&2
		cat "${log}" >&2
		rm -f "${log}"
		exit 1
	fi
}

show_help() {
	cat <<EOF
Usage: $(basename "$0") [options] [-- <init args>...]

Options:
  -u USER   Target user (required when running as root)
  -a NAME   Git repo author (default: ${DEFAULT_AUTHOR})
  -r NAME   Git repo name (default: ${DEFAULT_REPO})
  -b REF    Git branch or tag (default: ${DEFAULT_BRANCH})
  -h        Show this help

Everything after '--' is forwarded to '${APP_NAME} init' for
non-interactive installs (CI/Docker). Example:

  $(basename "$0") -u provider -- \\
      --modules ton-storage,ton-storage-provider \\
      --storage-path /var/ton-storage \\
      --storage-cost 10 --provider-space 100 \\
      --max-bag-size 40 --auto-update yes

Requires Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}.
On Ubuntu, a newer Python is auto-installed from deadsnakes PPA.
EOF
	exit 0
}

parse_args() {
	if [[ "${1-}" =~ ^-*h(elp)?$ ]]; then
		show_help
	fi
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
	# Everything after '--' is forwarded to 'mytonprovider init'.
	shift $((OPTIND - 1))
	init_args=("$@")
}

# Root with -u USER → proceed; root without -u → error; non-root → re-exec via sudo.
ensure_root_with_user() {
	if [[ "$(id -u)" == "0" ]]; then
		if [[ -z "${input_user}" ]]; then
			die "When running as root, pass -u USER." \
				"Or run as a non-root user (re-execs via sudo)."
		fi
		return
	fi

	local current_user current_groups
	current_user=$(whoami)
	current_groups=$(groups "${current_user}")

	local cmd=(
		bash "${0}"
		-u "${current_user}"
		-a "${author}"
		-r "${repo}"
		-b "${branch}"
	)
	if (( ${#init_args[@]} > 0 )); then
		cmd+=(-- "${init_args[@]}")
	fi
	if [[ "${current_groups}" == *"sudo"* ]]; then
		sudo "${cmd[@]}"
	else
		su root -c "$(printf '%q ' "${cmd[@]}")"
	fi
	exit $?
}

resolve_user_home() {
	local target="$1" home
	home=$(getent passwd "${target}" | cut -d: -f6)
	if [[ -z "${home}" || ! -d "${home}" ]]; then
		die "User '${target}' has no valid home directory"
	fi
	echo "${home}"
}

install_system_packages() {
	run_quiet apt update
	run_quiet apt install -y "${APT_BASE_PACKAGES[@]}"
}

# True if $1 is a python binary with version >= REQUIRED.
python_is_recent_enough() {
	local candidate="$1"
	command -v "${candidate}" >/dev/null 2>&1 || return 1
	"${candidate}" -c \
		"import sys; sys.exit(0 if sys.version_info >= (${REQUIRED_PYTHON_MAJOR}, ${REQUIRED_PYTHON_MINOR}) else 1)" \
		2>/dev/null
}

# Find first suitable python, set ${python_bin}.
detect_python() {
	local candidate
	for candidate in python3.12 python3.11 python3.10 python3; do
		if python_is_recent_enough "${candidate}"; then
			python_bin="${candidate}"
			return 0
		fi
	done
	return 1
}

install_fallback_python() {
	[[ -r /etc/os-release ]] || die "Cannot detect OS: /etc/os-release missing"
	# shellcheck source=/dev/null
	. /etc/os-release

	case "${ID:-}" in
		ubuntu)
			run_quiet add-apt-repository -y ppa:deadsnakes/ppa
			run_quiet apt update
			run_quiet apt install -y \
				"${FALLBACK_PYTHON}" \
				"${FALLBACK_PYTHON}-venv" \
				"${FALLBACK_PYTHON}-dev"
			;;
		*)
			die "Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} not found." \
				"Auto-install is supported on Ubuntu only (found: ${ID:-unknown})."
			;;
	esac
}

# Detect or install python, then install matching venv package.
ensure_python() {
	if detect_python; then
		install_matching_venv_package
		return
	fi
	install_fallback_python
	if ! detect_python; then
		die "Python install failed: still no Python" \
			">= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}"
	fi
}

install_matching_venv_package() {
	local pkg
	if [[ "${python_bin}" == "python3" ]]; then
		pkg="python3-venv"
	else
		pkg="${python_bin}-venv"
	fi
	run_quiet apt install -y "${pkg}"
}

create_venv() {
	local user="$1" venv_path="$2"
	local venvs_dir
	venvs_dir="$(dirname "${venv_path}")"
	mkdir -p "${venvs_dir}"
	chown "${user}:${user}" "${venvs_dir}"
	rm -rf "${venv_path}"
	run_quiet sudo -u "${user}" "${python_bin}" -m venv "${venv_path}"
	run_quiet sudo -u "${user}" "${venv_path}/bin/pip" install --upgrade pip
}

# pip install from git populates PEP 610 direct_url.json (needed for self-update).
install_package_from_git() {
	local user="$1" venv_path="$2"
	run_quiet sudo -u "${user}" "${venv_path}/bin/pip" install \
		"git+https://github.com/${author}/${repo}@${branch}"
}

# Init runs as root but resolves the target user via SUDO_USER cascade.
launch_init_wizard() {
	local user="$1" venv_bin="$2"
	shift 2
	SUDO_USER="${user}" "${venv_bin}" init "$@"
}

main() {
	parse_args "$@"
	ensure_root_with_user

	local user="${input_user}"
	local user_home venv_path venv_bin
	user_home=$(resolve_user_home "${user}")
	venv_path="${user_home}/.local/venv/${APP_NAME}"
	venv_bin="${venv_path}/bin/${APP_NAME}"

	step_start "Installing system packages"
	install_system_packages
	step_done

	step_start "Ensuring Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}"
	ensure_python
	step_done "${python_bin}"

	step_start "Creating virtualenv"
	create_venv "${user}" "${venv_path}"
	step_done

	step_start "Installing ${APP_NAME} package"
	install_package_from_git "${user}" "${venv_path}"
	[[ -x "${venv_bin}" ]] || die "No ${venv_bin} after install"
	step_done

	echo ""
	launch_init_wizard "${user}" "${venv_bin}" \
		${init_args[@]+"${init_args[@]}"}

	echo ""
	echo -e "${C_STEP}MyTonProvider installation completed${C_RESET}"
}

main "$@"
