FROM mcr.microsoft.com/devcontainers/base:jammy

# copy micromamba environment file
COPY app/env.yml /tmp/env.yml

# Install additional trusted CAs for developer environments (e.g., Zscaler)
COPY .devcontainer/*.crt /tmp/
COPY .devcontainer/install-custom-ca.sh /tmp/install-custom-ca.sh
RUN /tmp/install-custom-ca.sh

# install psql client
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
