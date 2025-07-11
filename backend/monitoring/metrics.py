from prometheus_client import Counter, Histogram, Gauge, generate_latest
from flask import Response
import time
import functools
import redis
import os

# Métriques Prometheus
REQUEST_COUNT = Counter(
    'rdtm_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'rdtm_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

REAL_DEBRID_API_CALLS = Counter(
    'rdtm_real_debrid_api_calls_total',
    'Total Real-Debrid API calls',
    ['endpoint', 'status_code']
)

REAL_DEBRID_RATE_LIMIT = Gauge(
    'rdtm_real_debrid_rate_limit_remaining',
    'Remaining Real-Debrid API calls',
    ['limit_type']
)

ACTIVE_TORRENTS = Gauge(
    'rdtm_active_torrents',
    'Number of active torrents',
    ['status']
)

CACHE_OPERATIONS = Counter(
    'rdtm_cache_operations_total',
    'Total cache operations',
    ['operation', 'result']
)

QUEUE_SIZE = Gauge(
    'rdtm_queue_size',
    'Current queue size',
    ['queue_type']
)

class MetricsCollector:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'))

    def track_request(self, f):
        """Décorateur pour tracker les requêtes HTTP"""
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                response = f(*args, **kwargs)
                status_code = getattr(response, 'status_code', 200)
                REQUEST_COUNT.labels(
                    method=request.method,
                    endpoint=request.endpoint or 'unknown',
                    status_code=status_code
                ).inc()
                
                return response
            except Exception as e:
                REQUEST_COUNT.labels(
                    method=request.method,
                    endpoint=request.endpoint or 'unknown',
                    status_code=500
                ).inc()
                raise
