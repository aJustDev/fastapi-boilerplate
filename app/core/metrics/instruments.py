from prometheus_client import Counter, Gauge, Histogram

# ── HTTP metrics ─────────────────────────────────────────────
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path_template", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path_template"],
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method"],
)

# ── Event bus metrics ────────────────────────────────────────
# Labelled by event type: a bounded set, the types the code publishes.
outbox_events_processed_total = Counter(
    "outbox_events_processed_total",
    "Outbox events whose handlers all succeeded",
    ["event_type"],
)

outbox_events_failed_total = Counter(
    "outbox_events_failed_total",
    "Outbox events that used up their retries and wait for a manual replay",
    ["event_type"],
)

# ── Database pool metrics ────────────────────────────────────
db_pool_size = Gauge(
    "db_pool_size",
    "Configured size of the database connection pool",
)

db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Number of connections currently checked out from the pool",
)

db_pool_checked_in = Gauge(
    "db_pool_checked_in",
    "Number of connections currently available in the pool",
)

db_pool_overflow = Gauge(
    "db_pool_overflow",
    "Number of connections beyond pool_size currently in use",
)
