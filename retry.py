import time
import random

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
    """计算带指数退避和随机抖动的延迟。"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay *= 1 + random.uniform(-jitter, jitter)
    return delay


def retry_call(func, args=None, kwargs=None, max_retries=DEFAULT_MAX_RETRIES,
               base_delay=DEFAULT_BASE_DELAY,
               retryable_exceptions=None):
    """调用函数并在指定异常时重试。

    参数:
        func: 要调用的可调用对象
        args: 位置参数元组（默认: ()）
        kwargs: 关键字参数字典（默认: {}）
        max_retries: 抛出异常前的最大重试次数
        base_delay: 初始延迟秒数
        retryable_exceptions: 要捕获并重试的异常类型元组

    返回:
        func 的返回值

    抛出:
        如果所有重试耗尽，抛出最后捕获的异常
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
