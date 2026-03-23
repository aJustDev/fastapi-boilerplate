# Metrics & Observability

## What it provides

Prometheus-compatible metrics endpoint at `GET /v1/metrics` that exposes request-level and infrastructure health data. Designed for scraping by Prometheus and visualization in Grafana.

The system tracks three categories of metrics:

- **HTTP request metrics** — count, latency distribution, and in-progress requests per endpoint
- **Database pool metrics** — connection pool utilization (checked out, available, overflow)

## Architecture

```
Request → PrometheusMiddleware → (records start time)
                                       ↓
                                  Application
                                       ↓
Response ← PrometheusMiddleware ← (observes duration, increments counters)

Prometheus ──scrape──→ GET /v1/metrics ──→ generate_latest()
                                              ↓
                                    update_db_pool_metrics(engine)
```

The `PrometheusMiddleware` is an ASGI middleware (outermost in the stack) that wraps every request to capture timing and status codes. DB pool metrics are updated on each scrape, not per-request.

## Metrics reference

### HTTP metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | `method`, `path_template`, `status` | Total HTTP requests processed |
| `http_request_duration_seconds` | Histogram | `method`, `path_template` | Request latency distribution (seconds) |
| `http_requests_in_progress` | Gauge | `method` | Requests currently being processed |

### Database pool metrics

| Metric | Type | Description |
|--------|------|-------------|
| `db_pool_size` | Gauge | Configured pool size |
| `db_pool_checked_out` | Gauge | Connections currently in use |
| `db_pool_checked_in` | Gauge | Connections available in pool |
| `db_pool_overflow` | Gauge | Connections beyond pool_size |

### Label conventions

- `path_template` uses the FastAPI route template (e.g., `/v1/items/{item_id}`), not the raw path. This prevents high-cardinality label explosion.
- `status` is the HTTP status code as a string (e.g., `"200"`, `"404"`).
- Requests to `/v1/metrics` and `/v1/health/*` are excluded from metrics to avoid self-referential noise.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_ENABLED` | `true` | Enable/disable the metrics middleware and endpoint |

## Quick start: Prometheus + Grafana

A pre-configured observability stack is included:

```bash
# Start Prometheus + Grafana (app must be running on port 8000)
docker compose -f docker-compose.observability.yml up -d

# Open Grafana (admin/admin)
open http://localhost:3001
```

The "FastAPI Overview" dashboard is auto-provisioned with request rate, latency percentiles, throughput by endpoint, DB pool status, error rate, and pool saturation panels.

- Prometheus UI: `http://localhost:9090`
- Grafana: `http://localhost:3001` (admin / admin)

### Custom Prometheus configuration

If you need a standalone Prometheus, add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "fastapi"
    scrape_interval: 15s
    metrics_path: "/v1/metrics"
    static_configs:
      - targets: ["api:8000"]
```

## Adding custom metrics

Define metrics in `app/core/metrics/instruments.py` and use them anywhere:

```python
# instruments.py
from prometheus_client import Counter

items_created_total = Counter(
    "items_created_total",
    "Total items created",
    ["category"],
)

# In your use case or service:
from app.core.metrics.instruments import items_created_total

items_created_total.labels(category="electronics").inc()
```

Available types: `Counter` (monotonically increasing), `Histogram` (distributions), `Gauge` (current value), `Summary` (quantiles).

## Grafana dashboard

The auto-provisioned "FastAPI Overview" dashboard includes:

| Panel | PromQL | Purpose |
|-------|--------|---------|
| Request Rate | `sum by (status) (rate(http_requests_total[1m]))` | Requests/s by status code |
| Latency Percentiles | `histogram_quantile(0.95, ...)` | p50, p95, p99 latency |
| Throughput by Endpoint | `sum by (path_template) (rate(http_requests_total[1m]))` | Per-endpoint traffic |
| DB Connection Pool | `db_pool_checked_out`, `db_pool_size`, etc. | Pool utilization |
| Error Rate | `sum(rate(...{status=~"5.."}[5m])) / sum(rate(...[5m]))` | 5xx percentage with thresholds |
| Pool Saturation | `db_pool_checked_out / db_pool_size * 100` | Gauge with green/yellow/red |

Dashboard source: `observability/grafana/dashboards/fastapi-overview.json`

## Limitations

- **In-memory, per-process**: Each uvicorn worker maintains its own counters. Prometheus aggregates across workers via the scrape target. If running multiple instances behind a load balancer, each needs its own scrape target.
- **No distributed tracing**: This implementation covers metrics only. OpenTelemetry can be added later for distributed tracing without conflicting with the current setup.
- **No authentication on `/metrics`**: Standard practice — restrict access via network/firewall in production.
