#!/usr/bin/env bash
#
# MyTonProvider install script.
#
# Installs system dependencies, ensures a recent-enough Python is
# available, creates a user-local venv, installs the mytonprovider
# package from git (populates PEP 610 direct_url.json so self-update
# works), and launches the init wizard.

set -euo pipefail

# Installed package name — matches ``constants.APP_NAME`` and the
# ``[project.scripts]`` entry in ``pyproject.toml``. Pip writes the
# venv binary as this name regardless of the git repository name, and
# the init wizard resolves venv/config paths through ``APP_NAME``, so
# the install target is ALWAYS canonical even when -a/-r/-b point at a
# fork.
readonly APP_NAME="mytonprovider"

readonly DEFAULT_AUTHOR="nessshon"
readonly DEFAULT_REPO="mytonprovider"
readonly DEFAULT_BRANCH="v1.0.0"

# Avoid interactive apt prompts (tzdata etc.) during unattended runs.
export DEBIAN_FRONTEND=noninteractive

readonly REQUIRED_PYTHON_MAJOR=3
readonly REQUIRED_PYTHON_MINOR=10

# Base system packages. Python and its venv package are handled
# separately because we may need to pull a newer Python from a PPA
# and install the matching venv package for it.
readonly APT_BASE_PACKAGES=(
	git
	curl
	wget
	fio
	build-essential
	software-properties-common
)

# Fallback Python version installed from deadsnakes when the distro
# default is older than REQUIRED_PYTHON_{MAJOR,MINOR}.
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

step() {
	local number="$1" total="$2" message="$3"
	echo -e "${C_STEP}[${number}/${total}]${C_RESET} ${message}"
}

show_help() {
	cat <<EOF
Usage: $(basename "$0") [options] [-- <init args>...]

Options:
  -u USER   Target (non-root) user to install under (required when running as root)
  -a NAME   Git repo author to install from (default: ${DEFAULT_AUTHOR})
  -r NAME   Git repo name to install from (default: ${DEFAULT_REPO})
  -b REF    Git branch or tag (default: ${DEFAULT_BRANCH})
  -h        Show this help

Everything after '--' is forwarded verbatim to '${APP_NAME} init', enabling
non-interactive installs (CI/Docker). Example:

  $(basename "$0") -u provider -- \\
      --modules ton-storage,ton-storage-provider \\
      --storage-path /var/ton-storage \\
      --storage-cost 10 --provider-space 100 --max-bag-size 40 \\
      --auto-update yes

With no '--' passthrough, '${APP_NAME} init' runs interactively (prompts).

The package is always installed as ${APP_NAME} under ~/.local/venv/${APP_NAME}
regardless of -a/-r/-b, because entry-point and init paths are hardcoded
to that name. -a/-r/-b only select the git source to pip-install from.

Requires Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}.
On Ubuntu, a newer Python is installed automatically from the deadsnakes PPA.
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
	# Anything after our own flags (normally after '--') is forwarded to
	# 'mytonprovider init' — enables non-interactive Docker/CI installs.
	shift $((OPTIND - 1))
	init_args=("$@")
}

# Guarantees: afterwards we are root and ${input_user} is set.
#   - root + -u USER  → proceed
#   - root without -u → abort (we never install under /root)
#   - non-root        → re-exec via sudo passing -u $(whoami)
ensure_root_with_user() {
	if [[ "$(id -u)" == "0" ]]; then
		if [[ -z "${input_user}" ]]; then
			die "When running as root, pass -u USER. Or run this script as a non-root user and it will re-exec via sudo."
		fi
		return
	fi

	local current_user current_groups
	current_user=$(whoami)
	current_groups=$(groups "${current_user}")

	local cmd=(bash "${0}" -u "${current_user}" -a "${author}" -r "${repo}" -b "${branch}")
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
	apt update
	apt install -y "${APT_BASE_PACKAGES[@]}"
}

# True if $1 binary exists AND runs Python >= REQUIRED_PYTHON_{MAJOR,MINOR}.
python_is_recent_enough() {
	local candidate="$1"
	command -v "${candidate}" >/dev/null 2>&1 || return 1
	"${candidate}" -c "import sys; sys.exit(0 if sys.version_info >= (${REQUIRED_PYTHON_MAJOR}, ${REQUIRED_PYTHON_MINOR}) else 1)" 2>/dev/null
}

# Sets ${python_bin} to the first candidate that meets the version
# requirement, or returns 1 if none found.
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
			add-apt-repository -y ppa:deadsnakes/ppa
			apt update
			apt install -y "${FALLBACK_PYTHON}" "${FALLBACK_PYTHON}-venv" "${FALLBACK_PYTHON}-dev"
			;;
		*)
			die "Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} not found and auto-install is supported only on Ubuntu (found: ${ID:-unknown}). Install a newer Python manually and re-run."
			;;
	esac
}

# After this the global ${python_bin} points to a binary that satisfies
# the version requirement and has a matching venv package installed.
ensure_python() {
	if detect_python; then
		install_matching_venv_package
		return
	fi

	install_fallback_python
	if ! detect_python; then
		die "Python install failed: still no Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}"
	fi
	# deadsnakes already installs ${FALLBACK_PYTHON}-venv above, so nothing extra.
}

install_matching_venv_package() {
	local pkg
	if [[ "${python_bin}" == "python3" ]]; then
		pkg="python3-venv"
	else
		pkg="${python_bin}-venv"
	fi
	apt install -y "${pkg}"
}

create_venv() {
	local user="$1" venv_path="$2"
	local venvs_dir
	venvs_dir="$(dirname "${venv_path}")"
	mkdir -p "${venvs_dir}"
	chown "${user}:${user}" "${venvs_dir}"
	rm -rf "${venv_path}"
	sudo -u "${user}" "${python_bin}" -m venv "${venv_path}"
	sudo -u "${user}" "${venv_path}/bin/pip" install --upgrade pip
}

# Install directly from git so PEP 610 direct_url.json is written.
# MytonproviderModule.get_installed_version reads it to resolve the
# currently installed channel for self-update.
install_package_from_git() {
	local user="$1" venv_path="$2"
	sudo -u "${user}" "${venv_path}/bin/pip" install \
		"git+https://github.com/${author}/${repo}@${branch}"
}

# The init command runs as root (module install() requires it) but
# resolves the target user via the SUDO_USER cascade — both for install
# ownership (cmd_init._resolve_user) and for locating the MyPyClass
# work_dir (__main__._resolve_app_home). Any extra arguments collected
# via install.sh's '--' passthrough are forwarded to 'mytonprovider init'
# so callers can trigger non-interactive mode (Docker/CI).
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

	step 1 5 "Installing base system packages"
	install_system_packages

	step 2 5 "Ensuring Python >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}"
	ensure_python
	echo "Using ${python_bin} ($("${python_bin}" --version 2>&1))"

	step 3 5 "Creating Python virtualenv at ${venv_path}"
	create_venv "${user}" "${venv_path}"

	step 4 5 "Installing ${APP_NAME} from ${author}/${repo}@${branch}"
	install_package_from_git "${user}" "${venv_path}"
	[[ -x "${venv_bin}" ]] || die "Installation produced no ${venv_bin} (entry point missing)"

	if (( ${#init_args[@]} > 0 )); then
		step 5 5 "Running '${APP_NAME} init' non-interactively"
	else
		step 5 5 "Launching '${APP_NAME} init' wizard"
	fi
	# Defensive ${arr[@]+"${arr[@]}"} expansion — empty arrays under
	# ``set -u`` trigger "unbound variable" on older bash (macOS 3.2).
	launch_init_wizard "${user}" "${venv_bin}" ${init_args[@]+"${init_args[@]}"}

	echo -e "${C_STEP}MyTonProvider installation completed${C_RESET}"
}

main "$@"
