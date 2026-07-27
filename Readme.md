## Hydro API Metrics Exporter

Python script to read the Hydro API job queue and yeald prometheus metrics.

Usage: 

```
hydro-api-exporter.py [-h] [-H POSTGRES] [-D DATABASE] [-u USERNAME] [-p PASSWORD] [-P PORT] [-Q QUEUE] [-f FREQUENCY] [-V] [-v VERBOSE]
```

| Option                      | Env Var   | Default   | Purpose |
|-----------------------------|-----------|-----------|---------|
| `-h`                        | n/a       | n/a       | Help    |
| `-H`                        | POSTGRES  | none      | Database Location |
| `-D`                        | DATABASE  | none      | Database Name |
| `-u`                        | USERNAME  | hydrology | Database user |
| `-p`                        | PASSWORD  | hydrology | Database user password |
| `-P`                        | PORT      | none      | Database port |
| `-Q`                        | QUEUE     | queue     | Queue table name |
| `-f`                        | FREQUENCY | 30s       | Frequency of sampling |
| `-V`                        | n/a       | n/a       | Display version |
| `-v`                        | DEBUG     | none      | Debug verbosity (0-255) |

The script also supports the pre-exiting `SPRING_DATASOURCE_URL` env var, 
to derive the default values for `POSTGRES`, `DATABASE`, and `PORT`.
USERNAME and PASSWORD may be derived from the `SPRING_DATASOURCE_USERNAME` and `SPRING_DATASOURCE_PASSWORD` env vars.

### Metrics

| Name | Type | Labels | Notes |
|------|------|--------|---------|
| `hydro_api_queue_error_count` | `counter` | `queue` | Error counter. Incremented when failing to parse the table |
| `hydro_api_queue_gauge`  | `gauge` | `queue`, `requesturi`, `status` | Number of job in queue |
| `hydro_api_queue_oldest` | `gauge` | `queue`, `requesturi`, `status` | Age of oldest `InProgress` job (s) |
| `hydro_api_queue_bucket` | `gauge` | `queue`, `le`, `requesturi`, `status` | Time waiting distribution of jobs in queue. `le` buckets are in minutes  1, 10, 30, 60, 120, 180, 240, 360, +Inf |

### Release

To Release add a new version tag beginning with a 'v'.


### To debug

Set up a port forward to the database:

```
kubectl --context ea -n hydro-production port-forward svc/rds-proxy --address localhost,172.17.0.1 5432:5432 &
```

Test connectivity:

```
docker run -it  --rm --name psql-client -e PGHOST=172.17.0.1 ... governmentpaas/psql:latest  psql
```

Build/Run the docker image:

```
make image run
```
