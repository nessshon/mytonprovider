#!/usr/bin/env bash
# Clone a Go package from GitHub, build the binary into /usr/local/bin,
# installing the latest Go toolchain when needed.
set -euo pipefail

readonly SRC_DIR="/usr/src"
readonly BIN_DIR="/usr/local/bin"
readonly GO_PATH="/usr/local/go/bin/go"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

show_help() {
    cat <<EOF
Usage: $(basename "$0") -a AUTHOR -r REPO -b REF -e ENTRY [-s SERVICE]

  -a AUTHOR   GitHub owner (e.g. xssnick)
  -r REPO     GitHub repository (e.g. tonutils-storage)
  -b REF      Git branch or tag to build
  -e ENTRY    Path to the main package (e.g. cli/main.go or storage-cli)
  -s SERVICE  Optional systemd service to restart after build
  -h          Show this help and exit
EOF
}

# ---- tasks ----

detect_arch() {
    local raw
    raw=$(dpkg --print-architecture 2>/dev/null || uname -m)
    case "${raw}" in
        x86_64)  printf 'amd64\n' ;;
        aarch64) printf 'arm64\n' ;;
        *)       printf '%s\n' "${raw}" ;;
    esac
}

install_go() {
    local arc go_ver tmp
    arc=$(detect_arch)
    go_ver=$(curl -s "https://go.dev/VERSION?m=text" | head -n 1)
    tmp=$(mktemp)
    rm -rf /usr/local/go
    wget -q "https://go.dev/dl/${go_ver}.linux-${arc}.tar.gz" -O "${tmp}"
    tar -C /usr/local -xzf "${tmp}"
    rm -f "${tmp}"
}

# Install/upgrade Go when go.mod requires a newer release than what's there.
check_go_version() {
    local need current
    local -i n1 n2 n3 c1 c2 c3
    [[ -x "${GO_PATH}" ]] || { install_go; return; }
    need=$(grep "^go " "$1" | head -n 1 | awk '{print $2}')
    current=$("${GO_PATH}" version | awk '{print $3}' | sed 's/^go//')
    IFS='.' read -r c1 c2 c3 <<<"${current}"
    IFS='.' read -r n1 n2 n3 <<<"${need}"
    c3=${c3:-0}; n3=${n3:-0}
    if (( c1 > n1 || (c1 == n1 && c2 > n2) || (c1 == n1 && c2 == n2 && c3 >= n3) )); then
        return
    fi
    install_go
}

clone_repository() {
    rm -rf "${SRC_PATH}_tmp"
    git clone --branch "${ref}" --recursive \
        "https://github.com/${author}/${repo}.git" "${SRC_PATH}_tmp"
    rm -rf "${SRC_PATH}"
    mv "${SRC_PATH}_tmp" "${SRC_PATH}"
    git config --system --add safe.directory "${SRC_PATH}" 2>/dev/null || true
}

# Build from the module root via ``go -C`` into a tmp file, then atomically
# move into place so a failed build never leaves a broken binary.
compile() {
    local tmp
    tmp=$(mktemp)
    env CGO_ENABLED=1 "${GO_PATH}" -C "${SRC_PATH}" build -o "${tmp}" "./${entry_point}"
    chmod 0755 "${tmp}"
    mv -f "${tmp}" "${BIN_PATH}"
}

service_restart() {
    [[ -n "${service_name}" ]] || return 0
    systemctl cat "${service_name}" >/dev/null 2>&1 || return 0
    systemctl restart "${service_name}"
}

main() {
    clone_repository
    check_go_version "${SRC_PATH}/go.mod"
    compile
    service_restart
}

# ---- arg parsing ----

author=""
repo=""
ref=""
entry_point=""
service_name=""

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then show_help; exit 0; fi
[[ "$(id -u)" == "0" ]] || die "must run as root"

while getopts "a:r:b:e:s:h" flag; do
    case "${flag}" in
        a) author="${OPTARG}" ;;
        r) repo="${OPTARG}" ;;
        b) ref="${OPTARG}" ;;
        e) entry_point="${OPTARG}" ;;
        s) service_name="${OPTARG}" ;;
        h) show_help; exit 0 ;;
        *) show_help; exit 1 ;;
    esac
done

[[ -n "${author}"      ]] || die "author (-a) is required"
[[ -n "${repo}"        ]] || die "repo (-r) is required"
[[ -n "${ref}"         ]] || die "ref (-b) is required"
[[ -n "${entry_point}" ]] || die "entry point (-e) is required"

readonly SRC_PATH="${SRC_DIR}/${repo}"
readonly BIN_PATH="${BIN_DIR}/${repo}"

main
