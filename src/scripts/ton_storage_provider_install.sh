#!/bin/bash
set -e

# Import functions: check_superuser, check_go_version
my_dir=$(dirname $(realpath ${0}))
. ${my_dir}/utils.sh

# Check sudo
check_superuser

# Default args
author="xssnick"
repo="tonutils-storage-provider"
branch="master"

# Install parameters
src_dir="/usr/src"
bin_dir="/usr/bin"
src_path="${src_dir}/${repo}"
bin_path="${bin_dir}/${repo}"
go_path="/usr/local/go/bin/go"

# Colors
COLOR='\033[95m'
ENDC='\033[0m'


clone_repository() {
	echo "https://github.com/${author}/${repo}.git -> ${branch}"
	rm -rf ${src_path}
	git clone --branch ${branch} --recursive https://github.com/${author}/${repo}.git ${src_path}
	git config --global --add safe.directory ${src_path}
}

install_required() {
	check_go_version "${src_path}/go.mod" ${go_path}
}

compilation() {
	echo "${src_path} -> ${bin_path}"
	cd ${src_path}
	#entry_point=$(find ${package_src_path} -name "main.go" | head -n 1)
	CGO_ENABLED=1 ${go_path} build -o ${bin_path} ${src_path}/cmd/main.go
}

ton_storage_provider_setup(){
	echo -e "${COLOR}[1/4]${ENDC} Cloning Ton-Storage-Provider repository"
	clone_repository

	echo -e "${COLOR}[2/4]${ENDC} Installing required packages"
	install_required

	echo -e "${COLOR}[3/4]${ENDC} Source compilation"
	compilation

	echo -e "${COLOR}[4/4]${ENDC} Ton-Storage-Provider installation complete"
}

ton_storage_provider_setup
exit 0
