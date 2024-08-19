FROM python:3.12-bookworm

RUN pip install "idf-component-manager~=2.0"

COPY upload.sh /upload.sh

ENTRYPOINT  ["/upload.sh"]
