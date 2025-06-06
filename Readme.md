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
| `-D`                        | DATABASE  | hydrology | Database Name |
| `-u`                        | USERNAME  | hydrology | Database user |
| `-p`                        | PASSWORD  | hydrology | Database user password |
| `-P`                        | PORT      | none      | Database port |
| `-Q`                        | QUEUE     | queue     | Queue table name |
| `-f`                        | FREQUENCY | 30s       | Frequency of sampling |
| `-V`                        | n/a       | n/a       | Display version |
| `-v`                        | DEBUG     | none      | Debug verbosity (0-255) |

The script also supports the pre-exiting `SPRING_DATASOURCE_URL` env var.

### Metrics

| Name | Type | Labels | Notes |
|------|------|--------|---------|
| `hydro_api_queue_gauge`  | `gauge` | `requesturi`, `status` | Number of job in queue |
| `hydro_api_queue_oldest` | `gauge` | `requesturi`, `status` | Age of oldest `InProgress` job (s) |
| `hydro_api_queue_bucket` | `gauge` | `le`, `requesturi`, `status` | Time waiting distribution of jobs in queue. `le` buckets are in minutes  1, 10, 30, 60, 120, 180, 240, 360, +Inf |

### Release

To Release add a new version tag beginning with a 'v'.
