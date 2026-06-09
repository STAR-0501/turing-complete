import time
import random
import functools

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_JITTER = 0.1


def exponential_backoff(
    attempt,
    base_delay=DEFAULT_BASE_DELAY,
    max_delay=DEFAULT_MAX_DELAY,
    jitter=DEFAULT_JITTER
):
    """Calculate delay with exponential backoff + random jitter."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay *= 1 + random.uniform(-jitter, jitter)
    return delay


def retry_call(func, args=None, kwargs=None, max_retries=DEFAULT_MAX_RETRIES,
               base_delay=DEFAULT_BASE_DELAY,
               retryable_exceptions=None):
    """Call func with retry on specified exceptions.

    Args:
        func: Callable to invoke
        args: Positional args tuple (default: ())
        kwargs: Keyword args dict (default: {})
        max_retries: Max retry attempts before re-raising
        base_delay: Initial delay in seconds
        retryable_exceptions: Tuple of exception types to catch and retry

    Returns:
        Whatever func returns

    Raises:
        The last exception caught, if all retries exhausted
    """
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}
    if retryable_exceptions is None:
        retryable_exceptions = (ConnectionError, TimeoutError, OSError)

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                delay = exponential_backoff(attempt, base_delay)
                time.sleep(delay)
    if last_exception is not None:
        raise last_exception


def retry(max_retries=DEFAULT_MAX_RETRIES, base_delay=DEFAULT_BASE_DELAY,
          retryable_exceptions=None):
    """Decorator: retry wrapped function on failure with exponential backoff."""
    if retryable_exceptions is None:
        retryable_exceptions = (ConnectionError, TimeoutError, OSError)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = exponential_backoff(attempt, base_delay)
                        time.sleep(delay)
            if last_exception is not None:
                raise last_exception
        return wrapper
    return decorator
