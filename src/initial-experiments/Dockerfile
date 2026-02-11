FROM aisiuk/inspect-tool-support
# Some of the models like to use ripgrep. Let them have it,
# both because it's interesting and because it avoids long
# grep commands from slowing down rollouts.
RUN apt-get install -y ripgrep

RUN apt-get install -y golang

# Use a non-root user with temporary passwordless sudo.
# (Temporary because the setup script removes that power.)
RUN apt-get install -y sudo
RUN groupadd -r user && useradd -r -g user user
RUN echo "user ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers
USER user

WORKDIR /home/user
