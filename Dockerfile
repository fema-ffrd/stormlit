# Use an official Python runtime as the base image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install streamlit
RUN pip install --no-cache-dir streamlit

# Copy any necessary files into the container
# In this case, we don't need to copy any files since we're using streamlit hello

# Expose the port Streamlit runs on
EXPOSE 8501

# Configure Streamlit to run on 0.0.0.0 to be accessible outside container
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Command to run your application
CMD ["streamlit", "hello"]