FROM mambaorg/micromamba:2.0.5 as builder

WORKDIR /app

USER root

RUN apt-get update && apt-get install build-essential -y \
    && apt-get clean

USER mambauser

COPY env.yml env.yml
COPY src src
COPY src/main.py src/main.py

RUN micromamba install -y -n base -f env.yml && \
    micromamba clean --all --yes

FROM mambaorg/micromamba:2.0.5

COPY --from=builder /opt/conda /opt/conda
COPY --from=builder /app /app

WORKDIR /app

# Expose the port Streamlit runs on
EXPOSE 8501

# Configure Streamlit to run on 0.0.0.0 to be accessible outside container
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Command to run your application
CMD ["streamlit", "run", "src/main.py"]
