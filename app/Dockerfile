FROM mambaorg/micromamba:2.3.0 AS builder

WORKDIR /app

USER root

RUN apt-get update && apt-get install build-essential -y \
    && apt-get clean

USER mambauser

COPY env.yml env.yml
RUN micromamba install -y -n base -f env.yml && \
    micromamba clean --all --yes

COPY src src
COPY src/main.py src/main.py
COPY .streamlit .streamlit

FROM mambaorg/micromamba:2.3.0

# fix for CVE-2024-10963 https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1087019
USER root
RUN echo "deb http://deb.debian.org/debian unstable main" > /etc/apt/sources.list.d/unstable.list && \
    apt-get update && \
    apt-get install -y -t unstable libpam0g libpam-modules libpam-modules-bin libpam-runtime && \
    rm /etc/apt/sources.list.d/unstable.list && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER mambauser

COPY --from=builder /opt/conda /opt/conda
COPY --from=builder /app /app

WORKDIR /app

# Expose the port Streamlit runs on
EXPOSE 8501

# Configure Streamlit to run on 0.0.0.0 to be accessible outside container
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Command to run your application
CMD ["streamlit", "run", "src/main.py"]
