FROM mambaorg/micromamba:2.0.5

WORKDIR /app

COPY env.yml env.yml
COPY src src
COPY main.py main.py

RUN micromamba install -y -n base -f env.yml && \
    micromamba clean --all --yes

# Expose the port Streamlit runs on
EXPOSE 8501

# Configure Streamlit to run on 0.0.0.0 to be accessible outside container
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Command to run your application
CMD ["streamlit", "run", "main.py"]