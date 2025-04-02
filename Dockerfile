FROM ubuntu:latest

RUN apt update && apt install -y sudo
#RUN useradd -m -s /bin/bash testuser && echo 'testuser:password123' | chpasswd
#RUN usermod -aG sudo testuser
RUN apt install git -y
RUN #cd /home/testuser/
RUN git clone https://github.com/seroburomalinoviy/mytonprovider.git
#USER testuser
RUN cd mytonprovider
RUN chmod +x /mytonprovider/install.sh

CMD ["./install.sh"]
