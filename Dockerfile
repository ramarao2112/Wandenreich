FROM python:3.12-slim

WORKDIR /app

# Copy all project files into the container
COPY . /app

# Install TrustC along with the server and attack harness dependencies
RUN pip install --no-cache-dir ".[harness,server]"

# Expose the default port
EXPOSE 8787

# Start the TrustC server bound to 0.0.0.0 so external traffic can reach it
CMD ["sh", "-c", "trustc serve --host 0.0.0.0 --port ${PORT:-8787} || uvicorn trustc.server:app --host 0.0.0.0 --port ${PORT:-8787}"]