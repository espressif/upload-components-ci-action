FROM python:3.12-bookworm

RUN pip install "idf-component-manager~=2.1"

COPY upload.py /upload.py

ENTRYPOINT  ["/upload.py"]
