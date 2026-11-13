FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir ".[harness,server]"

EXPOSE 8787

CMD ["sh", "-c", "trustc serve --host 0.0.0.0 --port ${PORT:-8787} || uvicorn trustc.server:app --host 0.0.0.0 --port ${PORT:-8787}"]
