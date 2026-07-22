FROM python:3.13.14-alpine3.24
RUN pip install prometheus_client requests psycopg2-binary python-json-logger
WORKDIR /
ADD epilog.py hydro-api-exporter.py /
EXPOSE 9898
CMD [ "python3", "-u", "/hydro-api-exporter.py" ]
