#!/bin/bash
set -e

#author=igroman787
author=seroburomalinoviy
repo=mytonprovider
current_dir=$(pwd)

# colors
COLOR='\033[92m'
ENDC='\033[0m'

# functions
show_help_and_exit() {
	echo 'Supported arguments:'
	echo ' -u  USER         Specify the user to be used for MyTonProvider installation'
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

install_option_utils() {
  apt install -y curl
  apt install -y wget
  apt install -y git
}

install_python311() {
  dist_info=$(grep "^PRETTY_NAME=" /etc/os-release | cut -d= -f2 | tr -d '"')
  dist_name=$(echo "${dist_info}" | cut -d " " -f 1)
  dist_version=$(echo "${dist_info}" | cut -d " " -f 2 | cut -d "." -f 1)
  py_version=$(python3.11 --version | cut -d " " -f 2)

  apt update

  echo "Current Python version: ${py_version}"

  if [[ "${py_version}" != "3.11"*  ]]; then
    if [[ ("${dist_name}" == "Ubuntu" && "${dist_version}" -ge 22) || (("${dist_name}" == "Debian" && "${dist_version}" -ge 12)) ]]; then
      apt install -y python3.11
    else
      apt install software-properties-common -y
      add-apt-repository ppa:deadsnakes/ppa -y
      apt update
    fi
    apt install -y python3.11
  fi

  apt install -y python3-pip
  apt install -y python3.11-venv

}

activate_venv() {
  python3.11 -m venv "${1}/venv"
  source "${1}/venv/bin/activate"
}

install_requirements() {
  pip install --upgrade pip
  pip install -r "${1}/mytonprovider/src/requirements.txt"
}

install_dependencies() {
  pip install -r "${1}/mytonprovider/mypylib/requirements.txt"
}

download_mytonprovider() {
  cd "${1}"
  git clone --recurse-submodules "https://github.com/${author}/${repo}"
}

launch_mtp() {
  python "${1}/mytonprovider/install.py"
}

install_mtp() {
  cd "/home/${user}"

  echo -e "${COLOR}[1/7]${ENDC} Installing utils"
  install_option_utils

  echo -e "${COLOR}[2/7]${ENDC} Installing python"
  install_python311

  echo -e "${COLOR}[3/7]${ENDC} Activating virtual environment"
  activate_venv "${current_dir}"

  echo -e "${COLOR}[4/7]${ENDC} Downloading MyTonProvider"
  download_mytonprovider "${current_dir}"

  echo -e "${COLOR}[5/7]${ENDC} Installing requirements"
  install_requirements "${current_dir}"

  echo -e "${COLOR}[6/7]${ENDC} Installing dependencies"
  install_dependencies "${current_dir}"

  echo -e "${COLOR}[7/7]${ENDC} Launching MyTonProvider"
  launch_mtp "${current_dir}"
}

install_mtp
exit 0




