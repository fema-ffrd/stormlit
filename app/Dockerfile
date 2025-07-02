FROM ubuntu:24.04 AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    tar \
    bzip2 \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install micromamba using the recommended method
RUN curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba \
    && mv bin/micromamba /usr/local/bin/micromamba \
    && chmod +x /usr/local/bin/micromamba

# Set up micromamba environment
ENV MAMBA_ROOT_PREFIX=/opt/micromamba
RUN /usr/local/bin/micromamba shell init -s bash -r /opt/micromamba

COPY env.yml env.yml
RUN eval "$(/usr/local/bin/micromamba shell hook -s posix)" && \
    micromamba install -y -n base -f env.yml && \
    micromamba clean --all --yes

COPY src src
COPY src/main.py src/main.py
COPY .streamlit .streamlit

FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    curl \
    tar \
    bzip2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install micromamba in final image
RUN curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba \
    && mv bin/micromamba /usr/local/bin/micromamba \
    && chmod +x /usr/local/bin/micromamba

ENV MAMBA_ROOT_PREFIX=/opt/micromamba
COPY --from=builder /opt/micromamba /opt/micromamba
COPY --from=builder /app /app

WORKDIR /app

# Expose the port Streamlit runs on
EXPOSE 8501

# Configure Streamlit to run on 0.0.0.0 to be accessible outside container
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Set up shell for micromamba
RUN /usr/local/bin/micromamba shell init -s bash -r /opt/micromamba

# Command to run your application
CMD ["bash", "-c", "eval \"$(/usr/local/bin/micromamba shell hook -s posix)\" && micromamba activate base && streamlit run src/main.py"]
