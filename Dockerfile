FROM python:3.12-bookworm

RUN pip install uv

WORKDIR /app

COPY uv.lock /app/uv.lock
COPY pyproject.toml /app/pyproject.toml
RUN uv --directory /app sync --locked

COPY upload.py /app/upload.py

ENTRYPOINT  ["uv", "--directory", "/app", "run", "/app/upload.py"]
