# Metrics

Prometheus metrics served at `GET /v1/metrics`: HTTP request counts, latency and requests in
flight, recorded by an ASGI middleware, plus database pool gauges read on each scrape.
`docker-compose.observability.yml` brings up Prometheus and Grafana with a ready dashboard.

## How it works

- `PrometheusMiddleware` (`app/core/metrics/middleware.py`) wraps every HTTP request except
  `/v1/metrics` and `/v1/health/*`. After the response it labels the request with the template of
  the route that served it, taken from `scope["route"]` and resolved to its full path with
  `fastapi.routing.iter_route_contexts` (once, on the first request). A request that matched no
  route is labeled `__unmatched__`; a wrong method on an existing path keeps the route template.
- `GET /v1/metrics` refreshes the pool gauges from the engine (`QueuePool` only) and returns the
  default registry in the Prometheus text format.

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method`, `path_template`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `path_template` (not observed for OPTIONS and HEAD) |
| `http_requests_in_progress` | Gauge | `method` |
| `db_pool_size`, `db_pool_checked_out`, `db_pool_checked_in`, `db_pool_overflow` | Gauge | |
| `outbox_events_processed_total` | Counter | `event_type` |
| `outbox_events_failed_total` | Counter | `event_type`: events out of retries, waiting for a replay |

The process collector of `prometheus_client` adds the standard `process_*` and `python_*` metrics.

## Usage

```bash
docker compose -f docker-compose.observability.yml up -d   # with the API on port 8000
# Grafana: http://localhost:3001 (admin/admin), dashboard "FastAPI Overview"
# Prometheus: http://localhost:9090
```

A standalone Prometheus scrapes `metrics_path: /v1/metrics`. A custom metric is declared in
`app/core/metrics/instruments.py` and used where the event happens:

```python
items_created_total = Counter("items_created_total", "Items created", ["category"])

items_created_total.labels(category=item.category).inc()
```

Keep label values bounded (categories, statuses), never ids or free text.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `METRICS_ENABLED` | `true` | Registers the recording middleware; `/v1/metrics` stays mounted either way |
| `METRICS_TOKEN` | empty | When set, `/v1/metrics` requires it as a bearer token |

## Guarantees and limits

- Label cardinality is bounded by the number of routes: raw paths never become labels.
- Counters live in each process. With `uvicorn --workers N` every scrape reaches one worker and
  returns only its counters, so totals jump between scrapes: run one process per container (and
  scale containers), or switch `prometheus_client` to multiprocess mode.
- `/v1/metrics` is open unless `METRICS_TOKEN` is set; with it, the scrape must send
  `Authorization: Bearer <token>` (Prometheus: `authorization: {credentials: <token>}` in the
  scrape config). Without a token, keep the endpoint on the internal network.
- Metrics only; there is no tracing.

## Files

| File | Role |
|---|---|
| `app/core/metrics/middleware.py` | `PrometheusMiddleware` |
| `app/core/metrics/instruments.py` | Metric definitions |
| `app/core/metrics/db_collector.py` | Pool gauges |
| `app/api/v1/metrics.py` | `GET /v1/metrics` |
| `observability/` | Prometheus and Grafana provisioning, dashboard JSON |
