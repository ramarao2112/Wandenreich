FROM python:3.12-slim

WORKDIR /app

# Install socat to bridge Render's public 0.0.0.0:$PORT to TrustC's 127.0.0.1:8787
RUN apt-get update && apt-get install -y --no-install-recommends socat && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir ".[harness,server]"

EXPOSE 8787

# Run TrustC on loopback (127.0.0.1:8788) and forward public 0.0.0.0:${PORT:-8787} to it
CMD ["sh", "-c", "trustc serve --host 127.0.0.1 --port 8788 & socat TCP-LISTEN:${PORT:-8787},bind=0.0.0.0,reuseaddr,fork TCP:127.0.0.1:8788"]
