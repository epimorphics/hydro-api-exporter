### Hydro API Metrics Exporter

Python script to read the Hydro API job queue and yeald prometheus metrics.

Usage: 

```
hydro-api-exporter.py [-h] [-H POSTGRES] [-D DATABASE] [-u USERNAME] [-p PASSWORD] [-P PORT] [-f FREQUENCY] [-V] [-v VERBOSE]
```

| Option                      | Env Var   | Default   | Purpose |
|-----------------------------|-----------|-----------|---------|
| `-h`                        | n/a       | n/a       | Help    |
| `-H`                        | POSTGRES  | none      | Database Location |
| `-D`                        | DATABASE  | hydrology | Database Name |
| `-u`                        | USERNAME  | hydrology | Database user |
| `-p`                        | PASSWORD  | hydrology | Database user password |
| `-P`                        | PORT      | none      | Database port |
| `-f`                        | FREQUENCY | 30s       | Frequency of sampling |
| `-V`                        | n/a       | n/a       | Display version |
| `-v`                        | DEBUG     | none      | Debug verbosity |

The script also supports the pre-exiting `SPRING_DATASOURCE_URL` env var.

### Release

To Release add a new version tag beginning with a 'v'.
