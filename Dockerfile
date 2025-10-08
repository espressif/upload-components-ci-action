FROM python:3.12-bookworm

RUN pip install uv
COPY uv.lock /uv.lock
COPY pyproject.toml /pyproject.toml
RUN uv sync --locked

COPY upload.py /upload.py

ENTRYPOINT  ["uv", "run", "/upload.py"]
