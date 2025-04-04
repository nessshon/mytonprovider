#!/bin/bash

check_superuser() {
	if [ "$(id -u)" != "0" ]; then
		echo "Please run script as root"
		exit 1
	fi
}

check_go_version() {
	go_mod_path=${1}
	go_path=${2}
	go_mod_text=$(cat ${go_mod_path}) || exit 1
	need_version_text=$(echo "${go_mod_text}" | grep "go " | head -n 1 | awk '{print $2}')
	current_version_text=$(${go_path} version | awk '{print $3}' | sed 's\go\\g')
	echo "start check_go_version function"
	echo "need_version: ${need_version_text}, current_version: ${current_version_text}"
	current_version_1=$(echo ${current_version_text} | cut -d "." -f 1)
	current_version_2=$(echo ${current_version_text} | cut -d "." -f 2)
	current_version_3=$(echo ${current_version_text} | cut -d "." -f 3)
	need_version_1=$(echo ${need_version_text} | cut -d "." -f 1)
	need_version_2=$(echo ${need_version_text} | cut -d "." -f 2)
	need_version_3=$(echo ${need_version_text} | cut -d "." -f 3)
	if (( current_version_1 > need_version_1 )); then
		return
	elif (( current_version_2 > need_version_2 )); then
		return
	elif (( current_version_3 >= need_version_3 )); then
		return
	else
		install_go
	fi
}

install_go() {
	echo "start install_go function"
	arc=$(dpkg --print-architecture)
	go_version_url=https://go.dev/VERSION?m=text
	go_version=$(curl -s ${go_version_url} | head -n 1)
	go_url=https://go.dev/dl/${go_version}.linux-${arc}.tar.gz
	rm -rf /usr/local/go
	wget -c ${go_url} -O - | tar -C /usr/local -xz
}
