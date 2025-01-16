# Stage 0: Use BuildKit's multi-platform support
FROM --platform=$BUILDPLATFORM python:3.12-slim as builder

# Set the working directory in the container
WORKDIR /app

# Stage 1: Create the final multi-arch image
FROM --platform=$TARGETPLATFORM python:3.12-slim

WORKDIR /app

# Install streamlit
RUN pip install --no-cache-dir streamlit

# Expose the port Streamlit runs on
EXPOSE 8501

# Configure Streamlit to run on 0.0.0.0 to be accessible outside container
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Command to run your application
CMD ["streamlit", "hello"]