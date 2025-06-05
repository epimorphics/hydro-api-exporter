FROM python:3.13.3-alpine3.21
RUN pip install prometheus_client requests psycopg2-binary
WORKDIR /
ADD hydro-api-exporter.py /
EXPOSE 9898
CMD [ "python3", "-u", "/hydro-api-exporter.py" ]
