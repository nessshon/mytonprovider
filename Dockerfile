FROM ubuntu:latest

RUN apt update && apt install -y sudo
RUN useradd -m -s /bin/bash testuser && echo 'testuser:password123' | chpasswd
RUN usermod -aG sudo testuser
USER testuser
RUN apt install git
RUN git clone https://github.com/seroburomalinoviy/mytonprovider.git
RUN cd mytonprovider

CMD ["bash"]
