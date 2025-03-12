#!/bin/bash
set -e

# colors
COLOR='\033[92m'
ENDC='\033[0m'

# functions
show_help_and_exit() {
	echo 'Supported arguments:'
	echo ' -u  USER         Specify the user to be used for MyTonCtrl installation'
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
	if [[ ${user_id} == 0 ]]; then
		echo "Please run script as non-root user"
		exit 1
	fi
	# Using sudo or su
	cmd="bash ${0} -u ${user}"
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
while getopts "u:h" flag; do
	case "${flag}" in
		u) input_user=${OPTARG};;
		h) show_help_and_exit;;
		*)
			echo "Flag -${flag} is not recognized. Aborting"
		exit 1 ;;
	esac
done

# Reboot yourself via root to continue the installation
restart_yourself_via_root


# Continue the installation
user=${input_user}
echo "Using user: ${user}"

