#!/bin/bash
set -e

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

check_go_version() { # перенести в локальный install_ton-storage.sh
	go_mod_path=${1}
	go_path=${2}
	go_mod_text=$(cat ${go_mod_path}) || exit 1
	need_version_text=$(echo "${go_mod_text}" | grep "go " | head -n 1 | awk '{print $2}')
	current_version_text=$(${go_path} version | awk '{print $3}' | sed 's\go\\g')
	echo "start check_go_version function, need_version: ${need_version_text}, current_version: ${current_version_text}"
	current_version_1=$(echo ${current_version_text} | cut -d "." -f 1)
	current_version_2=$(echo ${current_version_text} | cut -d "." -f 2)
	current_version_3=$(echo ${current_version_text} | cut -d "." -f 3)
	need_version_1=$(echo ${need_version_text} | cut -d "." -f 1)
	need_version_2=$(echo ${need_version_text} | cut -d "." -f 2)
	need_version_3=$(echo ${need_version_text} | cut -d "." -f 3)
	if (( need_version_1 > current_version_1 )) || ((need_version_2 > current_version_2 )) || ((need_version_3 > current_version_3 )); then
		install_go
	fi
}

install_go() {
  echo -e "${COLOR}[5/9]${ENDC} Installing Go"
	arc=$(dpkg --print-architecture)
	go_version_url=https://go.dev/VERSION?m=text
	go_version=$(curl -s ${go_version_url} | head -n 1)
	go_url=https://go.dev/dl/${go_version}.linux-${arc}.tar.gz
	rm -rf /usr/local/go
	wget -c ${go_url} -O - | tar -C /usr/local -xz
}

install_curl() {
  echo -e "${COLOR}[2/9]${ENDC} Installing Curl"
  apt install curl -y
}

install_wget() {
  echo -e "${COLOR}[3/9]${ENDC} Installing Wget"
  apt install wget -y
}

install_git() {
  echo -e "${COLOR}[4/9]${ENDC} Installing Git"
  apt install git -y
}

check_python_version () {
  echo "check python version"
  p3_version=$(python3 --version | cut -d " " -f 2)
  p3_major=$(echo ${p3_version} | cut -d "." -f 1)
  if [ "${p3_major}" != "3" ]; then
    install_python311
  fi
  p3_minor=$(echo ${p3_version} | cut -d "." -f 2)
  if [ ${p3_minor} -lt 11 ]; then
    install_python311
  fi
}

install_python311() {
  echo -e "${COLOR}[6/9]${ENDC} Installing Python 3.11"
  if [ "$(uname)" > "Ubuntu 22.04" ]; then
    apt update
    apt install python3.11
    apt install python3-pip
  fi
  if (("$(uname)" = "Ubuntu 20.04")) || (( "$(uname)" = "Debian 11" )); then
    apt install software-properties-common -y
    add-apt-repository ppa:deadsnakes/ppa -y
    apt update
    apt install python3.11
    apt install python3-pip
  fi
#  if (("$(uname)" = "CentOS")) || (( "$(uname)" = "Rocky" )); then
#    dnf install -y gcc gcc-c++ make
#    dnf install -y python3.11
#  fi
#  if (("$(uname)" = "Arch")); then
#    pacman -S python
#  fi

}


install_requirements() {
  echo -e "${COLOR}[8/9]${ENDC} Installing requirements"
  pip311=$(echo pip3.${p3_minor})
#  pip install --upgrade pip
  $pip311 install -r mytonprovider/src/requirements.txt
}

download_mytonprovider() {
  echo -e "${COLOR}[7/9]${ENDC} Downloading mytonprovider"
  git clone https://github.com/igroman787/mytonprovider
}

launch_mtp() {
  echo -e "${COLOR}[9/9]${ENDC} Installing mytonprovider"
  # проверить что собран бинарник tonutils-storage
  export STORAGE_CMD=/home/${user}/tonutils-storage  # изменить на абсолютный путь # передавать путь через аргументы

  DEFAULT_STORAGE_PATH=$(pwd)
  export DEFAULT_STORAGE_PATH # defaults vars in one file

  export STORAGE_PROVIDER_CMD=./tonutils-storage
  export TUNNEL_PROVIDER_CMD=./tonutils-storage

  python3.11 -m mytonprovider/install.py
}

install_mtp() {
  echo -e "${COLOR}[1/9]${ENDC} Preparing mytonprovider"
  cd ${user}

  install_option_utils
#  install_wget
#  install_git

#  check_go_version
  check_python_version

  download_mytonprovider
  install_requirements

  lauch_mtp
}

install_mtp
exit 0




