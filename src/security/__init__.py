"""
Security Module - Integration Point

Exports all security components for use in server_v2.py:
- Authentication & Authorization
- Rate Limiting
- Request Validation
- Resilience Patterns
- Monitoring & Observability
- Configuration Management
"""

from .auth import (
    RateLimiter,
    TokenManager,
    APIKeyValidator,
    RBACValidator,
    RequestValidator,
    AuditLog
)

from .resilience import (
    CircuitBreaker,
    RetryPolicy,
    Timeout,
    DeadLetterQueue,
    HealthChecker,
    circuit_breaker,
    retry_policy,
    dead_letter_queue,
    health_checker
)

from .monitoring import (
    ApplicationMetrics,
    RequestLogger,
    PerformanceMonitor,
    AlertingMetrics,
    metrics
)

from .hardening import (
    EnvironmentConfig,
    TLSConfig,
    SecretManager,
    DatabaseConfig,
    ConfigValidator,
    EnvironmentValidator,
    config,
    tls_config,
    db_config,
    secret_manager
)

import structlog
from typing import Callable, Optional
from fastapi import Request, HTTPException
from functools import wraps
import time

log = structlog.get_logger()


class SecurityMiddleware:
    """FastAPI middleware for security enforcement"""
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        api_key_validator: APIKeyValidator,
        request_logger: RequestLogger,
        metrics: ApplicationMetrics
    ):
        self.rate_limiter = rate_limiter
        self.api_key_validator = api_key_validator
        self.request_logger = request_logger
        self.metrics = metrics
    
    async def __call__(self, request: Request, call_next):
        """Process request through security chain"""
        
        # Start timer
        start_time = time.time()
        client_id = request.client.host if request.client else "unknown"
        
        try:
            # Log request
            self.request_logger.log_request(
                method=request.method,
                path=request.url.path,
                client_id=client_id
            )
            
            # Rate limiting
            endpoint = request.url.path
            if not self.rate_limiter.is_allowed(
                client_id=client_id,
                endpoint=endpoint,
                max_requests=100,
                window_seconds=60
            ):
                self.metrics.api_errors.increment({"endpoint": endpoint})
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            # Process request
            response = await call_next(request)
            
            # Log response
            latency_ms = (time.time() - start_time) * 1000
            self.request_logger.log_response(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=latency_ms,
                client_id=client_id
            )
            
            # Track metrics
            self.metrics.api_requests.increment({"endpoint": endpoint})
            self.metrics.api_latency.observe(latency_ms / 1000)
            
            if response.status_code >= 400:
                self.metrics.api_errors.increment({"endpoint": endpoint})
            
            return response
        
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self.request_logger.log_error(
                error_type=type(e).__name__,
                error_message=str(e),
                endpoint=request.url.path,
                details={"client_id": client_id, "latency_ms": latency_ms}
            )
            self.metrics.api_errors.increment({"endpoint": request.url.path})
            raise


def require_auth(permission: Optional[str] = None):
    """
    Decorator: Require authentication and optional permission
    
    Usage:
        @app.get("/api/admin")
        @require_auth("write:rca")
        def admin_endpoint(token=Depends(get_token)):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, token=None, **kwargs):
            if not token:
                raise HTTPException(status_code=401, detail="Missing token")
            
            payload = TokenManager.verify_token(token)
            
            if permission and not RBACValidator.has_permission(payload.get("role"), permission):
                raise HTTPException(status_code=403, detail="Permission denied")
            
            # Log access
            AuditLog.log_access(
                user_id=payload.get("sub"),
                action="api_call",
                resource=func.__name__,
                status="allowed" if not permission else "allowed_with_permission"
            )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def track_performance(service_name: str):
    """
    Decorator: Track service performance
    
    Usage:
        @track_performance("anomaly_detection")
        def detect_anomalies(data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = PerformanceMonitor.start_timer(service_name)
            try:
                result = await func(*args, **kwargs)
                latency = PerformanceMonitor.end_timer(service_name, start)
                log.info(
                    "service_completed",
                    service=service_name,
                    latency_ms=latency
                )
                return result
            except Exception as e:
                latency = PerformanceMonitor.end_timer(service_name, start)
                log.error(
                    "service_failed",
                    service=service_name,
                    latency_ms=latency,
                    error=str(e)
                )
                raise
        
        def sync_wrapper(*args, **kwargs):
            start = PerformanceMonitor.start_timer(service_name)
            try:
                result = func(*args, **kwargs)
                latency = PerformanceMonitor.end_timer(service_name, start)
                log.info(
                    "service_completed",
                    service=service_name,
                    latency_ms=latency
                )
                return result
            except Exception as e:
                latency = PerformanceMonitor.end_timer(service_name, start)
                log.error(
                    "service_failed",
                    service=service_name,
                    latency_ms=latency,
                    error=str(e)
                )
                raise
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def with_resilience(
    use_circuit_breaker: bool = True,
    use_retry: bool = True,
    timeout_seconds: int = 30
):
    """
    Decorator: Apply resilience patterns
    
    Usage:
        @with_resilience(timeout_seconds=10)
        async def fetch_from_db():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if use_circuit_breaker:
                try:
                    return circuit_breaker.call(
                        func,
                        *args,
                        **kwargs
                    )
                except Exception:
                    if use_retry:
                        return retry_policy.execute(
                            func,
                            *args,
                            **kwargs
                        )
                    raise
            
            if use_retry:
                return await retry_policy.execute(
                    func,
                    *args,
                    **kwargs
                )
            
            return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            if use_circuit_breaker:
                try:
                    return circuit_breaker.call(
                        func,
                        *args,
                        **kwargs
                    )
                except Exception:
                    if use_retry:
                        return retry_policy.execute(
                            func,
                            *args,
                            **kwargs
                        )
                    raise
            
            if use_retry:
                return retry_policy.execute(
                    func,
                    *args,
                    **kwargs
                )
            
            return func(*args, **kwargs)
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


__all__ = [
    # Auth
    "RateLimiter",
    "TokenManager",
    "APIKeyValidator",
    "RBACValidator",
    "RequestValidator",
    "AuditLog",
    # Resilience
    "CircuitBreaker",
    "RetryPolicy",
    "Timeout",
    "DeadLetterQueue",
    "HealthChecker",
    "circuit_breaker",
    "retry_policy",
    "dead_letter_queue",
    "health_checker",
    # Monitoring
    "ApplicationMetrics",
    "RequestLogger",
    "PerformanceMonitor",
    "AlertingMetrics",
    "metrics",
    # Hardening
    "EnvironmentConfig",
    "TLSConfig",
    "SecretManager",
    "DatabaseConfig",
    "ConfigValidator",
    "EnvironmentValidator",
    "config",
    "tls_config",
    "db_config",
    "secret_manager",
    # Middleware & Decorators
    "SecurityMiddleware",
    "require_auth",
    "track_performance",
    "with_resilience",
]
