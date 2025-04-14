#!/bin/bash
set -e

# Check superuser
if [ "$(id -u)" != "0" ]; then
	echo "Please run script as root"
	exit 1
fi

# Colors
COLOR='\033[95m'
ENDC='\033[0m'

# Set default arguments
author="igroman787"
repo="mytonprovider"
branch="dev"

# Install parameters
src_dir="/usr/src"
bin_dir="/usr/bin"
src_path="${src_dir}/${repo}"
bin_path="${bin_dir}/${repo}"
go_path="/usr/local/go/bin/go"


clone_repository() {
	echo "https://github.com/${author}/${repo}.git -> ${branch}"
	rm -rf ${src_path}
	git clone --branch ${branch} --recursive https://github.com/${author}/${repo}.git ${src_path}
	git config --global --add safe.directory ${src_path}
}

clone_repository
exit 0
