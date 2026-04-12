#!/usr/bin/env bash
#
# Build and install a Go package from a GitHub repository.
# Called by TonStorageModule / TonStorageProviderModule during install and update.

set -euo pipefail

readonly C_STEP='\033[92m'
readonly C_ERROR='\033[91m'
readonly C_RESET='\033[0m'

die() {
	echo -e "${C_ERROR}${*}${C_RESET}" >&2
	exit 1
}

step() {
	local number="$1" total="$2" message="$3"
	echo -e "${C_STEP}[${number}/${total}]${C_RESET} ${message}"
}

# Run silently; dump full output only on failure.
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
	die "Please run script as root"
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
	die "Error: -b and -t are mutually exclusive"
fi
if [[ -z "${branch}" ]] && [[ -z "${tag}" ]]; then
	die "Error: one of -b or -t must be provided"
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
	local arc go_version go_url tmp_archive
	arc=$(dpkg --print-architecture)
	go_version=$(curl -s "https://go.dev/VERSION?m=text" | head -n 1)
	go_url="https://go.dev/dl/${go_version}.linux-${arc}.tar.gz"
	tmp_archive=$(mktemp)
	rm -rf /usr/local/go
	run_quiet wget -q "${go_url}" -O "${tmp_archive}"
	run_quiet tar -C /usr/local -xzf "${tmp_archive}"
	rm -f "${tmp_archive}"
}

clone_repository() {
	local ref="${tag:-${branch}}"
	rm -rf "${SRC_PATH}_tmp"
	run_quiet git clone --branch "${ref}" --recursive \
		"https://github.com/${author}/${repo}.git" "${SRC_PATH}_tmp"
	rm -rf "${SRC_PATH}"
	mv "${SRC_PATH}_tmp" "${SRC_PATH}"
	git config --system --add safe.directory "${SRC_PATH}" 2>/dev/null || true
}

compile() {
	cd "${SRC_PATH}"
	run_quiet env CGO_ENABLED=1 "${GO_PATH}" build -o "${BIN_PATH}" "${SRC_PATH}/${entry_point}"
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
	step 1 4 "Cloning ${repo} repository"
	clone_repository

	step 2 4 "Installing required packages"
	check_go_version "${SRC_PATH}/go.mod" "${GO_PATH}"

	step 3 4 "Source compilation"
	compile
	service_restart

	step 4 4 "${repo} installation complete"
}

main "$@"
