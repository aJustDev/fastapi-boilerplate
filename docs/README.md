# Docs

One doc per feature or structural piece: what it is, how it works, how to use it, its
configuration, guarantees and limits, and its files. Diagrams are generated from
`img/<topic>.py`.

## Structure

- [architecture.md](architecture.md): bounded contexts, layers, import rules, the registry, adding a context
- [database.md](database.md): sessions per request, engine and timeouts, models, repositories
- [migrations.md](migrations.md): Alembic workflow, safe changes on tables with data
- [configuration.md](configuration.md): where settings come from, validators, adding a setting

## Features

- [auth.md](auth.md): tokens, rotation, reuse detection, logout, roles and permissions
- [event-bus.md](event-bus.md): transactional outbox, dispatch with several workers
- [jobs.md](jobs.md): scheduled jobs, claims and leases
- [errors.md](errors.md): the error contract and its codes
- [security.md](security.md): proxies, hosts, security headers, rate limits

## Operations

- [deployment.md](deployment.md): required settings, migrations, first admin, what goes in front
- [operations.md](operations.md): health endpoints, the command line, running the workers
- [logging.md](logging.md): JSON and colored logs, request ids
- [metrics.md](metrics.md): Prometheus metrics and dashboards
- [docker.md](docker.md): the image and compose
- [testing.md](testing.md): test levels, fixtures, meta-tests
- [tooling.md](tooling.md): hooks, CI, audit, Dependabot, lint and type rules

## Decisions

- [adr/](adr/README.md): architecture decision records
