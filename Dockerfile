FROM python:3.12-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir ".[harness,server]"

# Create a lightweight ASGI wrapper that normalizes Host/Origin headers to 127.0.0.1:8787
RUN python -c 'import pathlib; pathlib.Path("/app/cloud_entry.py").write_text("""\
import inspect\n\
import trustc.server as srv\n\
\n\
def _load_app():\n\
    for name in ("create_app", "build_app", "make_app", "get_app"):\n\
        fn = getattr(srv, name, None)\n\
        if callable(fn):\n\
            return fn()\n\
    for _, obj in inspect.getmembers(srv):\n\
        if callable(obj) and any(k in getattr(obj, "__name__", "").lower() for k in ("app", "server")):\n\
            try:\n\
                res = obj()\n\
                if callable(res):\n\
                    return res\n\
            except TypeError:\n\
                pass\n\
    raise RuntimeError("Could not locate ASGI app factory in trustc.server")\n\
\n\
_inner_app = _load_app()\n\
\n\
async def app(scope, receive, send):\n\
    if scope["type"] in ("http", "websocket"):\n\
        new_headers = []\n\
        for k, v in scope.get("headers", []):\n\
            kl = k.lower()\n\
            if kl == b"host":\n\
                new_headers.append((b"host", b"127.0.0.1:8787"))\n\
            elif kl == b"origin":\n\
                new_headers.append((b"origin", b"http://127.0.0.1:8787"))\n\
            elif kl == b"referer":\n\
                new_headers.append((b"referer", b"http://127.0.0.1:8787/"))\n\
            else:\n\
                new_headers.append((k, v))\n\
        scope = dict(scope)\n\
        scope["headers"] = new_headers\n\
        scope["server"] = ("127.0.0.1", 8787)\n\
        scope["client"] = ("127.0.0.1", 50000)\n\
    await _inner_app(scope, receive, send)\n\
""")'

EXPOSE 8787

CMD ["sh", "-c", "uvicorn cloud_entry:app --host 0.0.0.0 --port ${PORT:-8787}"]
