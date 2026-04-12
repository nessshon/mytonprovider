#!/usr/bin/env bash
#
# Build and install a Go package from a GitHub repository.
# Called by TonStorageModule / TonStorageProviderModule during install and update.

set -euo pipefail

readonly C_STEP='\033[92m'
readonly C_RESET='\033[0m'

author=""
repo=""
branch=""
tag=""
entry_point=""
service_name=""

show_help() {
	cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -a NAME   Git author
  -r NAME   Git repo
  -b REF    Git branch (mutually exclusive with -t)
  -t REF    Git tag (mutually exclusive with -b)
  -e PATH   Entry point for compilation (e.g. cli/main.go)
  -s NAME   Service name to restart after build
  -h        Show this help
EOF
	exit 0
}

if [[ "${1-}" =~ ^-*h(elp)?$ ]]; then
	show_help
fi

if [[ "$(id -u)" != "0" ]]; then
	echo "Please run script as root"
	exit 1
fi

while getopts "a:r:b:t:e:s:h" flag; do
	case "${flag}" in
		a) author="${OPTARG}" ;;
		r) repo="${OPTARG}" ;;
		b) branch="${OPTARG}" ;;
		t) tag="${OPTARG}" ;;
		e) entry_point="${OPTARG}" ;;
		s) service_name="${OPTARG}" ;;
		h) show_help ;;
		*)
			echo "Unrecognized flag. Aborting"
			exit 1
			;;
	esac
done

if [[ -n "${branch}" ]] && [[ -n "${tag}" ]]; then
	echo "Error: -b and -t are mutually exclusive"
	exit 1
fi
if [[ -z "${branch}" ]] && [[ -z "${tag}" ]]; then
	echo "Error: one of -b or -t must be provided"
	exit 1
fi

readonly SRC_DIR="/usr/src"
readonly BIN_DIR="/usr/local/bin"
readonly SRC_PATH="${SRC_DIR}/${repo}"
readonly BIN_PATH="${BIN_DIR}/${repo}"
readonly GO_PATH="/usr/local/go/bin/go"

check_go_version() {
	local go_mod_path="$1" go_bin="$2"
	if [[ ! -f "${go_bin}" ]]; then
		install_go
		return
	fi

	local need current
	need=$(grep "^go " "${go_mod_path}" | head -n 1 | awk '{print $2}')
	current=$("${go_bin}" version | awk '{print $3}' | sed 's/go//')

	local cur1 cur2 cur3 need1 need2 need3
	IFS='.' read -r cur1 cur2 cur3 <<< "${current}"
	IFS='.' read -r need1 need2 need3 <<< "${need}"
	cur3="${cur3:-0}"
	need3="${need3:-0}"

	if (( cur1 > need1 )); then return; fi
	if (( cur1 == need1 && cur2 > need2 )); then return; fi
	if (( cur1 == need1 && cur2 == need2 && cur3 >= need3 )); then return; fi
	install_go
}

install_go() {
	local arc go_version go_url
	arc=$(dpkg --print-architecture)
	go_version=$(curl -s "https://go.dev/VERSION?m=text" | head -n 1)
	go_url="https://go.dev/dl/${go_version}.linux-${arc}.tar.gz"
	rm -rf /usr/local/go
	wget -c "${go_url}" -O - | tar -C /usr/local -xz
}

clone_repository() {
	local ref="${tag:-${branch}}"
	echo "https://github.com/${author}/${repo}.git -> ${ref}"
	rm -rf "${SRC_PATH}_tmp"
	git clone --branch "${ref}" --recursive \
		"https://github.com/${author}/${repo}.git" "${SRC_PATH}_tmp"
	rm -rf "${SRC_PATH}"
	mv "${SRC_PATH}_tmp" "${SRC_PATH}"
	# Allow non-root users (daemon) to read git metadata for update checks.
	git config --global --add safe.directory "${SRC_PATH}"
}

compile() {
	echo "${SRC_PATH} -> ${BIN_PATH}"
	cd "${SRC_PATH}"
	CGO_ENABLED=1 "${GO_PATH}" build -o "${BIN_PATH}" "${SRC_PATH}/${entry_point}"
}

service_restart() {
	if [[ -z "${service_name}" ]]; then
		return
	fi
	if ! systemctl cat "${service_name}" >/dev/null 2>&1; then
		echo "Service ${service_name} not yet registered — skipping restart"
		return
	fi
	systemctl restart "${service_name}"
}

main() {
	echo -e "${C_STEP}[1/4]${C_RESET} Cloning ${repo} repository"
	clone_repository

	echo -e "${C_STEP}[2/4]${C_RESET} Installing required packages"
	check_go_version "${SRC_PATH}/go.mod" "${GO_PATH}"

	echo -e "${C_STEP}[3/4]${C_RESET} Source compilation"
	compile
	service_restart

	echo -e "${C_STEP}[4/4]${C_RESET} ${repo} installation complete"
}

main
