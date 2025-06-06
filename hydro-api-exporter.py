#! /usr/bin/python3

import argparse
import datetime
import json
import os
import psycopg2
import signal
import sys
import time

from _thread import *
import prometheus_client

version = "v0.1.5"

# Log in json for fluentd
def report(level, msg, jobs=None):
  event = {}
  event['timestamp'] = rfc3339(int(time.time()))
  event['level'] = level
  event['message'] = msg
  if jobs:
    for status in jobs:
      if status != 'Total':
        event[status] = str(jobs[status]['Total'])
  print(json.dumps(event))

# Format a epoach seconds time to log format time
def rfc3339(epoch):
  return datetime.datetime.fromtimestamp(epoch).isoformat('T') + 'Z'


def debug(msg):
  if (args.verbose > 0):
    report('debug', msg)


def log(msg, jobs=None):
  report('info', msg, jobs)


def warn(msg):
  report('warn', msg)


def error(msg):
  report('error', msg)


# Signal Catch, shutdown
def terminateProcess(signalNumber, frame):
  log('Received signal {}.'.format(signalNumber))
  if connection:
    connection.close()
  log('Connection closed. Terminating.')
  sys.exit()


# Connect to DB
def dbconnect():
  global connection
  connection = None

  while connection is None:
    try:
      connection = psycopg2.connect(
        host=args.postgres,
        database=args.database,
        user=args.username,
        password=args.password,
        port=args.port,
        connect_timeout=10
      )
    except (psycopg2.DatabaseError, Exception) as exception:
      error('Failed to connect to database {}:{}/{} as user {}: {}'.format(args.postgres, args.port, args.database, args.username, exception))
      time.sleep(10)

  log('Connected to database {}:{}/{} as user {}'.format(args.postgres, args.port, args.database, args.username))


# Real work here
def record(rows):
  now = int(time.time()) # Don't need faction of a second precision

  age = {}       # Age of oldest InProgress job by requesturi
  hist = {}      # Distribution of InProgress jobs by requesturi
  jobs = {}      # Count of jobs by requesturi and status

  buckets = [1,10,30,60,120,180,240,360] # histogram buckets (minutes)

  # initialise jobs
  jobs['Total'] = 0
  for status in ['Completed', 'Failed', 'InProgress']:
    jobs[status] = {}
    jobs[status]['Total'] = 0

  # loop through the db table
  for row in rows:
    if (args.verbose & 128): debug(row)

    jobs['Total'] += 1

    index      = row[0]
    requesturi = row[1]
    status =     row[2]
    starttime =  row[3]

    # initise the counters for a new requesturi
    if requesturi not in jobs[status]:
      jobs[status][requesturi] = 0

    if requesturi not in age:
      age[requesturi] = 0

    if requesturi not in hist:
      hist[requesturi] = {}
      for bucket in buckets:
        hist[requesturi][str(bucket)] = 0
      hist[requesturi]['+Inf'] = 0

    # increment job counters
    jobs[status][requesturi] += 1
    jobs[status]['Total'] += 1

    if (status == 'Completed'):
      if (args.verbose & 64): debug('index:{} requesturi:{} status:{}'.format(index, requesturi, status))
    else:
      elapsed_seconds = (now - int(starttime/1000))
      if elapsed_seconds < 0:
        warn('Queue entry has future start time index:{} requesturi:{} status:{} starttime:{}'.format(index, requesturi, status, starttime))
        break

      if (status == 'Failed'):
        if (args.verbose & 32): debug('index:{} requesturi:{} status:{} elapsed:{}'.format(index, requesturi, status, elapsed_seconds))
      else:
        if (args.verbose & 16): debug('index:{} requesturi:{} status:{} elapsed:{}'.format(index, requesturi, status, elapsed_seconds))

        # Increment the bucket count for elapsed time, or the catch-all bucket
        if (args.verbose & 4): debug('{}: index:{} requesturi:{} starttime:{} waiting:{}s'.format(status, index, requesturi, starttime, elapsed_seconds))
        allocated = 0
        for bucket in buckets:
          if allocated ==0 and elapsed_seconds < (60*bucket):
            allocated = 1
            hist[requesturi][str(bucket)] += 1
            if (args.verbose & 4): debug('Histogram[{}][{}][{}] incemented to {}'.format(requesturi, status, bucket, hist[requesturi][str(bucket)]))
        if allocated == 0:
          hist[requesturi]['+Inf'] += 1
          if (args.verbose & 4): debug('Histogram[{}][{}][+Inf] incemented to {}'.format(requesturi, status, hist[requesturi]['+Inf']))

        # update oldest
        if requesturi in age:
          if (elapsed_seconds > age[requesturi]):
            if (args.verbose & 2): debug('Oldest[{}][{}] updated {}'.format(requesturi, status, elapsed_seconds))
            age[requesturi] = elapsed_seconds
        else:
          if (args.verbose & 2): debug('Oldest[{}][{}] set {}'.format(requesturi, status, elapsed_seconds))
          age[requesturi] = elapsed_seconds

  # set the count metrics. Note Totals only used by the output log.
  for status in jobs:
    if status != 'Total':
      for requesturi in jobs[status]:
        if requesturi != 'Total':
          queue.labels(requesturi = requesturi, status = status).set(jobs[status][requesturi])

  # Set the metric for the oldest
  for requesturi in age:
    if (args.verbose & 2): debug('Metric oldest[{}][{}] set {}'.format(requesturi, status, age[requesturi]))
    oldest.labels(requesturi = requesturi, status = 'InProgress').set(age[requesturi])

  # Set the distribution metric
  for requesturi in hist:
    msg = 'Histogram[{}] |'.format(requesturi)
    for bucket in hist[requesturi]:
      msg = '{}{} ({})|'.format(msg, hist[requesturi][bucket], bucket)
      inprogress.labels(le=bucket, requesturi = requesturi, status = 'InProgress').set(hist[requesturi][bucket])
    if (args.verbose & 8):
      debug(msg)

  return (jobs)


def dbread():
  global connection

  while True:
    # having the sleep at the start of the loop helps with the ingress
    # transfer from one exiting pod to a new running one.
    time.sleep(args.frequency)
    try:
      if (args.verbose & 1): debug('Reading hydri-api queue from table ({}).'.format(args.queue))
      with connection.cursor() as cur:
        cur.execute('select index, requesturi, status, startTime from {}'.format(args.queue))
        jobs = record(cur.fetchall())
      log('Read {} {} from hydro-api queue({}).'.format(jobs['Total'], "row" if (jobs['Total']==1) else "rows", args.queue), jobs)
    except (psycopg2.DatabaseError, Exception) as exception:
      error(exception)


def process():
  if (args.verbose): debug('Started version {}'.format(version))
  dbconnect()
  # start prometheus metrics
  # if we wait until the DB connection is made then this is a readiness probe
  prometheus_client.start_http_server(9898)

  # Now really go do some work
  dbread()


if __name__ == "__main__":
  # Read the JDBC env var form defaults.
  jdbc = os.environ.get('SPRING_DATASOURCE_URL', 'jdbc:postgresql://:/')

  # Arg Parse Command line options with default specific env vars, ultimately using jdbc string.
  parser = argparse.ArgumentParser()
  parser.add_argument('-H', '--hostname', dest='postgres', help='Database location', action='store', default=os.environ.get('POSTGRES', jdbc.split(':')[2].split('/')[2]))
  parser.add_argument('-D', '--database', dest='database', help='Database name', action='store', default=os.environ.get('DATABASE', jdbc.split(':')[3].split('/')[1] ))
  parser.add_argument('-u', '--useranme', dest='username', help='User name', action='store', default=os.environ.get('USERNAME', os.environ.get('SPRING_DATASOURCE_USERNAME', 'hydrology')))
  parser.add_argument('-p', '--password', dest='password', help='Password', action='store', default=os.environ.get('PASSWORD', os.environ.get('SPRING_DATASOURCE_PASSWORD', 'hydrology')))
  parser.add_argument('-P', '--port', dest='port', help='Port', action='store', default=os.environ.get('PORT', jdbc.split(':')[3].split('/')[0]))
  parser.add_argument('-f', '--frequency', dest='frequency', help='How often the queus is read in seconds', action='store', default=60, type=int)
  parser.add_argument('-Q', '--queue',   dest='queue', help='The table name holding the queue', action='store', default=(os.environ.get('QUEUE', 'queue')))
  parser.add_argument('-V', '--version', action='version', version='%(prog)s {}'.format(version))
  parser.add_argument('-v', '--verbose', dest='verbose', help='Verbose=1 to enable debug logging', action='store', default=int(os.environ.get('DEBUG', '0')), type=int)
  args = parser.parse_args()

  # Ensure environment is sufficient
  # A new pod will start giving chance to fix the env.
  if args.postgres is None:
    error('Location of database not defined.')
    sys.exit(1)

  if args.database is None:
    error('Name of database not defined.')
    sys.exit(1)

  if args.username is None:
    error('Database username of database not defined.')
    sys.exit(1)

  if args.password is None:
    error('Database password not defined.')
    sys.exit(1)

  if args.port is None:
    error('Database port not defined.')
    sys.exit(1)

  if args.queue is None:
    error('Queue table name not defined.')
    sys.exit(1)

  # We don't need Promethemus to monitor this process or the system
  prometheus_client.disable_created_metrics()

  prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
  prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
  prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

  # Define the Prometheus metrics:
  # 1. How many items in the queue by requesturi and status
  queue = prometheus_client.Gauge(
    'hydro_api_queue_gauge',
    'Jobs Status',
    ['requesturi', 'status']
    )

  # 2. The oldest by requesturi (and status) but only relevant to 'InProgress'
  oldest = prometheus_client.Gauge(
    'hydro_api_queue_oldest',
    'Longest time a job is waiting in queue',
    ['requesturi', 'status'],
    )

  # 3. A 'fake' histogram of jobs in the queue distrubuted over time waiting
  # Note a true histogram is a counter so every job would be counter multiple
  # times if one was used here.
  # Grafana (or anything else) doesn't seem to mind the other two metrics that
  # come with a true histogram. The count is already accounded to in 1. above
  # and the total sum has no useful meaning here.
  inprogress = prometheus_client.Gauge(
    'hydro_api_queue_bucket',
    'Hydro API job queue distribution',
    ['requesturi', 'status', 'le']
    )

  # register the signals to be caught
  signal.signal(signal.SIGINT, terminateProcess)
  signal.signal(signal.SIGQUIT, terminateProcess)
  signal.signal(signal.SIGTERM, terminateProcess)

  # Now go do some work
  process()
