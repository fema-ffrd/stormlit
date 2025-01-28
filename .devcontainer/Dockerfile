FROM mcr.microsoft.com/devcontainers/base:jammy

# copy micromamba environment file
COPY app/env.yml /tmp/env.yml

# Install additional trusted CAs for developer environments (e.g., Zscaler)
COPY .devcontainer/*.crt /tmp/
COPY .devcontainer/install-custom-ca.sh /tmp/install-custom-ca.sh
RUN /tmp/install-custom-ca.sh
