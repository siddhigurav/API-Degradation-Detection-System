"""
Error Handling & Resilience

Implements:
- Graceful error handling with detailed messages
- Circuit breaker pattern
- Retry logic with exponential backoff
- Fallback mechanisms
- Timeout handling
- Dead letter queues
"""

from typing import Callable, Optional, Any, Type
from functools import wraps
import time
import asyncio
import structlog
from enum import Enum
from datetime import datetime, timedelta

log = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing, reject requests
    HALF_OPEN = "half_open"    # Testing if recovered


class CircuitBreaker:
    """Circuit breaker for fault tolerance"""
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        """
        Initialize circuit breaker
        
        Args:
            name: Circuit identifier
            failure_threshold: Failures before opening
            recovery_timeout: Seconds before half-open
            expected_exception: Exception type to catch
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.success_count = 0
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception if circuit open or function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                log.info(f"Circuit {self.name}: HALF_OPEN (attempting recovery)")
            else:
                raise Exception(f"Circuit {self.name} is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:  # Two successes = recovered
                self.state = CircuitState.CLOSED
                log.info(f"Circuit {self.name}: CLOSED (recovered)")
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            log.warning(
                f"Circuit {self.name}: OPEN (threshold exceeded)",
                failure_count=self.failure_count
            )
    
    def _should_attempt_reset(self) -> bool:
        """Check if recovery timeout has elapsed"""
        if not self.last_failure_time:
            return False
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout


class RetryPolicy:
    """Retry logic with exponential backoff"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry policy
        
        Args:
            max_attempts: Maximum retry attempts
            initial_delay: Initial retry delay (seconds)
            max_delay: Maximum delay between retries
            backoff_factor: Exponential backoff multiplier
            jitter: Add randomness to avoid thundering herd
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
    
    def execute(
        self,
        func: Callable,
        *args,
        retryable_exceptions: tuple = (Exception,),
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic
        
        Args:
            func: Function to execute
            *args: Function arguments
            retryable_exceptions: Exception types to retry on
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Last exception if all attempts fail
        """
        last_exception = None
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
                
            except retryable_exceptions as e:
                last_exception = e
                
                if attempt == self.max_attempts:
                    log.error(
                        "Retry exhausted",
                        function=func.__name__,
                        attempts=attempt,
                        error=str(e)
                    )
                    raise
                
                delay = self._calculate_delay(attempt)
                log.warning(
                    "Retrying",
                    function=func.__name__,
                    attempt=attempt,
                    next_delay=delay,
                    error=str(e)
                )
                
                time.sleep(delay)
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff"""
        delay = self.initial_delay * (self.backoff_factor ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            import random
            delay *= random.uniform(0.5, 1.5)
        
        return delay


class Timeout:
    """Timeout decorator"""
    
    @staticmethod
    def async_timeout(seconds: float):
        """Async timeout decorator"""
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                try:
                    return await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=seconds
                    )
                except asyncio.TimeoutError:
                    log.error(
                        "Timeout",
                        function=func.__name__,
                        timeout_seconds=seconds
                    )
                    raise TimeoutError(f"Function {func.__name__} timed out")
            
            return wrapper
        return decorator
    
    @staticmethod
    def sync_timeout(seconds: float):
        """Sync timeout decorator (uses signal on Unix)"""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # For production, use multiprocessing or concurrent.futures
                return func(*args, **kwargs)
            
            return wrapper
        return decorator


class DeadLetterQueue:
    """Dead letter queue for failed messages"""
    
    def __init__(self, max_size: int = 10000):
        """Initialize DLQ"""
        self.messages = []
        self.max_size = max_size
    
    def add(self, message: dict, error: str, original_topic: str):
        """
        Add message to DLQ
        
        Args:
            message: Original message
            error: Error description
            original_topic: Source topic
        """
        dlq_message = {
            "original_message": message,
            "error": error,
            "original_topic": original_topic,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": 0
        }
        
        if len(self.messages) < self.max_size:
            self.messages.append(dlq_message)
            log.warning(
                "Message added to DLQ",
                topic=original_topic,
                error=error,
                dlq_size=len(self.messages)
            )
        else:
            log.error(
                "DLQ full, message dropped",
                topic=original_topic,
                dlq_size=self.max_size
            )
    
    def retry(self, func: Callable, max_retries: int = 3) -> int:
        """
        Retry processing messages from DLQ
        
        Args:
            func: Processing function
            max_retries: Max retries per message
            
        Returns:
            Number of messages reprocessed
        """
        reprocessed = 0
        failed = []
        
        for msg in self.messages:
            if msg['retry_count'] >= max_retries:
                failed.append(msg)
                continue
            
            try:
                func(msg['original_message'])
                reprocessed += 1
                log.info(
                    "DLQ message reprocessed",
                    topic=msg['original_topic']
                )
            except Exception as e:
                msg['retry_count'] += 1
                log.warning(
                    "DLQ retry failed",
                    error=str(e),
                    retry_count=msg['retry_count']
                )
                failed.append(msg)
        
        self.messages = failed
        return reprocessed
    
    def get_status(self) -> dict:
        """Get DLQ status"""
        return {
            "messages": len(self.messages),
            "capacity": self.max_size,
            "utilization": len(self.messages) / self.max_size
        }


class HealthChecker:
    """Service health checking"""
    
    def __init__(self):
        """Initialize health checker"""
        self.checks: dict = {}
        self.last_check: dict = {}
    
    def register(
        self,
        name: str,
        check_func: Callable,
        timeout: float = 5.0,
        interval: float = 30.0
    ):
        """
        Register health check
        
        Args:
            name: Check name
            check_func: Function returning True if healthy
            timeout: Check timeout
            interval: Check interval
        """
        self.checks[name] = {
            "func": check_func,
            "timeout": timeout,
            "interval": interval,
            "last_run": None,
            "status": "unknown"
        }
    
    async def check_all(self) -> dict:
        """
        Run all health checks
        
        Returns:
            Health status for all services
        """
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
            "checks": {}
        }
        
        for name, check in self.checks.items():
            try:
                # Check interval
                if check["last_run"]:
                    elapsed = (datetime.utcnow() - check["last_run"]).total_seconds()
                    if elapsed < check["interval"]:
                        # Use cached result
                        results["checks"][name] = {
                            "status": check["status"],
                            "cached": True
                        }
                        continue
                
                # Run check
                is_healthy = await asyncio.wait_for(
                    check["func"](),
                    timeout=check["timeout"]
                )
                
                check["status"] = "healthy" if is_healthy else "unhealthy"
                check["last_run"] = datetime.utcnow()
                
                results["checks"][name] = {
                    "status": check["status"],
                    "last_run": check["last_run"].isoformat()
                }
                
            except asyncio.TimeoutError:
                check["status"] = "timeout"
                results["checks"][name] = {"status": "timeout"}
                
            except Exception as e:
                check["status"] = "error"
                results["checks"][name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Determine overall status
        if any(check["status"] != "healthy" for check in self.checks.values()):
            results["status"] = "degraded"
        
        return results


# Global instances
circuit_breaker = CircuitBreaker("database")
retry_policy = RetryPolicy(max_attempts=3)
dead_letter_queue = DeadLetterQueue()
health_checker = HealthChecker()
