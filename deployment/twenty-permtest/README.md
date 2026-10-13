# Twenty permission test instance

This is an isolated local Compose project for Twenty v2.45.0 permission testing.
It has its own PostgreSQL, Redis, attachment storage, network, and Docker volumes.
It must only be initialized with synthetic test data. Do not restore the YIHE
database backup or attach this project to the `cra-twenty` volumes/network.

## Start

The ignored `.env` file contains instance-specific credentials and must be kept
local. Start from this directory:

```sh
docker compose up -d
docker compose ps
```

Open `http://localhost:3010`. The first-run setup creates the isolated workspace.
The configured mail driver is `logger`; no SMTP credentials are configured.

## Stop and remove

Stop while retaining test data:

```sh
docker compose down
```

Remove the test instance and its data after confirming the project name:

```sh
docker compose down --volumes --remove-orphans
```

The named volumes are explicitly prefixed `cra-twenty-permtest_`; never run the
cleanup command from `deployment/twenty` or against the `cra-twenty` project.
