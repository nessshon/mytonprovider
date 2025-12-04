#!/bin/bash
set -e

# Set default arguments
author="igroman787"
repo="mytonprovider"
branch="master"
ignore=false

# Colors
COLOR='\033[95m'
ENDC='\033[0m'

# functions
show_help_and_exit() {
	echo 'Supported arguments:'
	echo ' -u  USER         Specify the user to be used for MyTonProvider installation'
	echo ' -a               Set MyTonProvider git repo author'
	echo ' -r               Set MyTonProvider git repo'
	echo ' -b               Set MyTonProvider git repo branch'
	echo ' -i               Ignore non-root user checking'
	echo ' -h               Show this help'
	exit
}

restart_yourself_via_root() {
	# Check for input_user
	if [[ "${input_user}" != "" ]]; then
		return
	fi

	# Get vars
	user=$(whoami)
	user_id=$(id -u)
	user_groups=$(groups ${user})

	# Check is running as a normal user
	if [[ ${user_id} == 0 ]] && [[ ${ignore} == false ]]; then
		echo "Please run script as non-root user. You can create a new non-root user with command 'sudo adduser'. Or use flag '-i' to ignore this check."
		exit 1
	fi

	# Using sudo or su
	cmd="bash ${0} -u ${user} -a ${author} -r ${repo} -b ${branch}"
	if [[ ${user_groups} == *"sudo"* ]]; then
		sudo ${cmd}
		exit
	else
		su root -c "${cmd}"
		exit
	fi
}

# Show help for --help
if [[ "${1-}" =~ ^-*h(elp)?$ ]]; then
	show_help_and_exit
fi

# Input args
while getopts "u:a:r:b:ih" flag; do
	case "${flag}" in
		u) input_user=${OPTARG};;
		a) author=${OPTARG};;
		r) repo=${OPTARG};;
		b) branch=${OPTARG};;
		i) ignore=true;;
		h) show_help_and_exit;;
	esac
done

# Reboot yourself via root to continue the installation
restart_yourself_via_root

# Continue the installation
user=${input_user}
echo "Using user: ${user}"

# Install parameters
src_dir="/usr/src"
bin_dir="/usr/bin"
venvs_dir="/home/${user}/.local/venv"
venv_path="${venvs_dir}/${repo}"
src_path="${src_dir}/${repo}"

cd "${src_dir}"


clone_repository() {
	echo "https://github.com/${author}/${repo}.git -> ${branch}"
	rm -rf ${repo}_tmp
	git clone --branch ${branch} --recursive https://github.com/${author}/${repo}.git ${repo}_tmp
	rm -rf ${repo}
	mv ${repo}_tmp ${repo}
}

install_apt_dependencies() {
	apt update
	apt install -y $(cat ${src_path}/resources/pkglist.txt)
}

activate_venv() {
	virtualenv ${venv_path}
	source ${venv_path}/bin/activate
}

install_pip_dependencies() {
	pip3 uninstall -y pytoniq tonutils || true
	pip3 install -r ${src_path}/resources/requirements.txt
	pip3 install -r ${src_path}/mypylib/requirements.txt
}

download_global_config() {
	mkdir -p /var/ton
	wget https://igroman787.github.io/global.config.json -O /var/ton/global.config.json
	chown ${user}:${user} /var/ton/global.config.json
}

service_restart() {
	systemctl restart mytonproviderd
}


# Start update
clone_repository
install_apt_dependencies
activate_venv
install_pip_dependencies
download_global_config
service_restart
exit 0
