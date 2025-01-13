FROM python:3.13-bookworm

RUN pip install "idf-component-manager~=2.1"

COPY upload.py /upload.py

ENTRYPOINT  ["/upload.py"]
