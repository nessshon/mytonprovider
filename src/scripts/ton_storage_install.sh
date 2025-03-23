#!/bin/bash
set -e

# install parameters
src_path=/usr/src

storage_path=$1
storage_size=$2

author=xssnick
repo=tonutils-storage
branch=master
bin_name=ton_storage

# Colors
COLOR='\033[95m'
ENDC='\033[0m'

check_go_version() {
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
	echo "start install_go function"
	arc=$(dpkg --print-architecture)
	go_version_url="https://go.dev/VERSION?m=text"
	go_version=$(curl -s "${go_version_url}" | head -n 1)
	go_url=https://go.dev/dl/${go_version}.linux-${arc}.tar.gz
	rm -rf /usr/local/go
	wget -c ${go_url} -O - | tar -C /usr/local -xz
}

download_ton_utils() {
  package_src_path="${src_path}/${repo}"
  rm -rf ${package_src_path}

  cd ${src_path}
  git clone --branch=${branch} --recursive https://github.com/${author}/${repo}.git
}

install_options() {
  go_path=/usr/local/go/bin/go
  check_go_version "${package_src_path}/go.mod" ${go_path}
}

compilation() {
  db_path="/var/${bin_name}"
  mkdir -p ${db_path}
  cd ${package_src_path}
  #entry_point=$(find ${package_src_path} -name "main.go" | head -n 1)
  CGO_ENABLED=1 ${go_path} build -o ${db_path}/${bin_name} ${package_src_path}/cli/main.go
}

configuration() {
  cd ${package_src_path}
  # rewrite downloads path
  sed -e '/DownloadsPath/d' -e "1a/\"DownloadsPath\": \"${storage_path}\"," tonutils-storage-db/config.json
  # set storage size

}

setup_policy() {
  chown -R ${user}:${user} ${db_path}
}

ton_storage_setup(){
  echo -e "${COLOR}[1/6]${ENDC} Cloning github repository"
  download_ton_utils

  echo -e "${COLOR}[2/6]${ENDC} Installing required packages"
  install_options

  echo -e "${COLOR}[3/6]${ENDC} Source compilation"
  compilation

  echo -e "${COLOR}[4/6]${ENDC} Configuration"
  configuration

  echo -e "${COLOR}[5/6]${ENDC} ${bin_name} Setting policy"
  setup_policy

  echo -e "${COLOR}[6/6]${ENDC} ${bin_name} Installation complete"
}
ton_storage_setup
exit 0