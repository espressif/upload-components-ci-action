FROM python:3.10-bullseye

RUN pip install git+https://github.com/espressif/idf-component-manager.git@main

COPY upload.sh /upload.sh

ENTRYPOINT  ["/upload.sh"]
