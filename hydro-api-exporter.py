#! /usr/bin/python3

from epilog import EpiLog
logger = EpiLog(__name__)

import argparse
import datetime
import json
import os
import psycopg2
import signal
import sys
import time
import traceback

from _thread import *
import prometheus_client

version = "v0.2.1"


def error(msg, error=None):
  logger.error(msg, extra={'error': error})


def log(msg, jobs=None):
  event = {}
  if jobs:
    for status in jobs:
      if status != 'Total':
        event[status] = str(jobs[status]['Total'])
    logger.info(msg, extra=json.dump(event))
  else:
    logger.info(msg)


# Signal Catch, shutdown
def terminateProcess(signalNumber, frame):
  logger.notice('Received signal {}'.format(signalNumber))
  if connection:
    connection.close()
  log('Connection closed. Terminating')
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
    except Exception as exception:
      error('Failed to connect to database {}:{}/{} as user {}'.format(args.postgres, args.port, args.database, args.username), repr(exception))
      if (args.verbose & 128): logger.debug('Password:{}'.format(args.password))
      time.sleep(10)

  logger.notice('Connected to database {}:{}/{} as user {}'.format(args.postgres, args.port, args.database, args.username))


# Real work here
def record(rows):
  now = int(time.time()) # Don't need faction of a second precision

  age = {}       # Age of oldest InProgress/Pending job by requesturi
  age['InProgress'] = {} # Age of oldest InProgress job by requesturi
  age['Pending'] = {}    # Age of oldest Pending job by requesturi
  hist = {}      # Distribution of jobs by status/requesturi
  hist['InProgress'] = {} # Distribution of InProgress jobs by requesturi
  hist['Pending'] = {}    # Distribution of Pending jobs by requesturi
  jobs = {}      # Count of jobs by requesturi and status

  factor = {}    # Factor to convert bucket to seconds
  buckets = {}   # Buckets for histogram

  factor['InProgress'] = 1
  buckets['InProgress'] = [1,2,4,8,16,32,64,128] # histogram buckets (seconds)
  factor['Pending'] = 60
  buckets['Pending'] = [1,10,30,60,120,180,240,360] # histogram buckets (minutes)

  # initialise jobs
  jobs['Total'] = 0
  for status in ['Completed', 'Failed', 'InProgress', 'Pending']:
    jobs[status] = {}
    jobs[status]['Total'] = 0

  print('Read {} rows from hydro-api queue({}).'.format(len(rows), args.queue))

  # loop through the db table
  for row in rows:
    if (args.verbose & 128): logger.debug(row)
    print('{}: index:{} requesturi:{} status:{}'.format(jobs['Total'], row[0], row[1], row[2]))

    jobs['Total'] += 1

    index      = row[0]
    requesturi = row[1]
    status =     row[2]
    starttime =  row[3]

    # initise histogram
    for s in ['InProgress', 'Pending']:
      if requesturi not in hist[s]:
        hist[s][requesturi] = {}
        for bucket in buckets[s]:
          hist[s][requesturi][str(bucket)] = 0
        hist[s][requesturi]['+Inf'] = 0

    # initise the counters for a new requesturi
    if requesturi not in jobs[status]:
      jobs[status][requesturi] = 0

    # increment job counters
    jobs[status][requesturi] += 1
    jobs[status]['Total'] += 1

    if (status == 'Completed'):
      if (args.verbose & 64): logger.debug('index:{} requesturi:{} status:{}'.format(index, requesturi, status))
    elif starttime is None:
      logger.warn('Queue entry has no start time index:{} requesturi:{} status:{}'.format(index, requesturi, status))
    else:
      elapsed_seconds = (now - int(starttime/1000))
      if elapsed_seconds < 0:
        logger.warn('Queue entry has future start time index:{} requesturi:{} status:{} starttime:{}'.format(index, requesturi, status, starttime))
        break

      if (status == 'Failed'):
        if (args.verbose & 32): logger.debug('index:{} requesturi:{} status:{} elapsed:{}'.format(index, requesturi, status, elapsed_seconds))
      else:
        if (args.verbose & 16): logger.debug('index:{} requesturi:{} status:{} elapsed:{}'.format(index, requesturi, status, elapsed_seconds))

        # Increment the bucket count for elapsed time, or the catch-all bucket
        if (args.verbose & 4): logger.debug('{}: index:{} requesturi:{} starttime:{} waiting:{}s'.format(status, index, requesturi, starttime, elapsed_seconds))
        allocated = 0
        for bucket in buckets[status]:
          if allocated ==0 and elapsed_seconds < (factor[status]*bucket):
            allocated = 1
            hist[status][requesturi][str(bucket)] += 1
            if (args.verbose & 4): logger.debug('Histogram[{}][{}][{}] incemented to {}'.format(requesturi, status, bucket, hist[status][requesturi][str(bucket)]))
        if allocated == 0:
          hist[status][requesturi]['+Inf'] += 1
          if (args.verbose & 4): logger.debug('Histogram[{}][{}][+Inf] incemented to {}'.format(requesturi, status, hist[status][requesturi]['+Inf']))

        if requesturi in age[status]:
          if (elapsed_seconds > age[status][requesturi]):
            if (args.verbose & 2): logger.debug('Oldest[{}][{}] updated {}'.format(requesturi, status, elapsed_seconds))
            age[status][requesturi] = elapsed_seconds
        else:
          if (args.verbose & 2): logger.debug('Oldest[{}][{}] set {}'.format(requesturi, status, elapsed_seconds))
          age[status][requesturi] = elapsed_seconds

  # set the count metrics. Note Totals only used by the output log.
  for status in jobs:
    if status != 'Total':
      for requesturi in jobs[status]:
        if requesturi != 'Total':
          length.labels(queue = args.queue, requesturi = requesturi, status = status).set(jobs[status][requesturi])

  # Set the metric for the oldest
  for status in ['InProgress', 'Pending']:
    for requesturi in age[status]:
      if (args.verbose & 2): logger.debug('Metric oldest[{}][{}] set {}'.format(requesturi, status, age[status][requesturi]))
      oldest.labels(queue = args.queue, requesturi = requesturi, status = status).set(age[status][requesturi])

  # Set the distribution metric
  for status in ['InProgress', 'Pending']:
    for requesturi in hist[status]:
      msg = 'Histogram[{}][{}] |'.format(status, requesturi)
      for bucket in hist[status][requesturi]:
        msg = '{}{} ({})|'.format(msg, hist[status][requesturi][bucket], bucket)
        histogram.labels(le=bucket, queue = args.queue, requesturi = requesturi, status = status).set(hist[status][requesturi][bucket])
      if (args.verbose & 8):
        logger.debug(msg)

  return (jobs)


def dbread():
  global connection

  while True:
    # having the sleep at the start of the loop helps with the ingress
    # transfer from one exiting pod to a new running one.
    time.sleep(args.frequency)
    try:
      if (args.verbose & 1): logger.debug('Reading hydri-api queue from table ({}).'.format(args.queue))
      with connection.cursor() as cur:
        cur.execute('select index, requesturi, status, startTime from {}'.format(args.queue))
        jobs = record(cur.fetchall())
      log('Read {} {} from hydro-api queue({}).'.format(jobs['Total'], "row" if (jobs['Total']==1) else "rows", args.queue), jobs)
    except Exception as exception:
      error('Failed to read from table {}'.format(args.queue), traceback.format_exc())


def process():
  if (args.verbose): logger.notice('Started version {}'.format(version))
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
  if args.postgres in (None, ''):
    error('Failed to start', 'Location of database not defined')
    sys.exit(1)

  if args.database in (None, ''):
    error('Failed to start', 'Name of database not defined')
    sys.exit(1)

  if args.username in (None, ''):
    error('Failed to start', 'Database username of database not defined')
    sys.exit(1)

  if args.password in (None, ''):
    error('Failed to start', 'Database password not defined')
    sys.exit(1)

  if args.port in (None, ''):
    error('Failed to start', 'Database port not defined')
    sys.exit(1)

  if args.queue is None:
    error('Failed to start', 'Queue table name not defined')
    sys.exit(1)

  # We don't need Promethemus to monitor this process or the system
  prometheus_client.disable_created_metrics()

  prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
  prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
  prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

  # Define the Prometheus metrics:
  # 1. How many items in the queue by requesturi and status
  length = prometheus_client.Gauge(
    'hydro_api_queue_gauge',
    'Jobs Status',
    ['queue', 'requesturi', 'status']
    )

  # 2. The oldest by requesturi (and status) but only relevant to 'InProgress' & 'Pending'
  oldest = prometheus_client.Gauge(
    'hydro_api_queue_oldest',
    'Longest time a job is waiting in queue',
    ['queue', 'requesturi', 'status'],
    )

  # 3. A 'fake' histogram of jobs in the queue distrubuted over time waiting
  # Note a true histogram is a counter so every job would be counter multiple
  # times if one was used here.
  # Grafana (or anything else) doesn't seem to mind the other two metrics that
  # come with a true histogram. The count is already accounded to in 1. above
  # and the total sum has no useful meaning here.
  histogram = prometheus_client.Gauge(
    'hydro_api_queue_bucket',
    'Hydro API job queue distribution',
    ['queue', 'requesturi', 'status', 'le']
    )

  # register the signals to be caught
  signal.signal(signal.SIGINT, terminateProcess)
  signal.signal(signal.SIGQUIT, terminateProcess)
  signal.signal(signal.SIGTERM, terminateProcess)

  # Now go do some work
  process()

# vim: set ts=2 sw=2 et:
