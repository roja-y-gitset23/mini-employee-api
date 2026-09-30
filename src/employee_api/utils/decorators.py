"""Reusable decorators."""

import functools
import inspect
import time
from typing import Any, Callable, TypeVar, cast

from employee_api.utils.logger import get_logger

F = TypeVar("F", bound=Callable[..., Any])

_logger = get_logger("employee_api.execution")


def log_execution(func: F) -> F:
    """Log start, end, duration and failures of a sync or async callable.

    Arguments are intentionally not logged to avoid leaking personal data.
    """
    name = func.__qualname__

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            _logger.info("START %s", name)
            try:
                result = await func(*args, **kwargs)
            except Exception:
                elapsed = (time.perf_counter() - start) * 1000
                _logger.exception("FAILED %s after %.2f ms", name, elapsed)
                raise
            elapsed = (time.perf_counter() - start) * 1000
            _logger.info("END %s in %.2f ms", name, elapsed)
            return result

        return cast(F, async_wrapper)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        _logger.info("START %s", name)
        try:
            result = func(*args, **kwargs)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            _logger.exception("FAILED %s after %.2f ms", name, elapsed)
            raise
        elapsed = (time.perf_counter() - start) * 1000
        _logger.info("END %s in %.2f ms", name, elapsed)
        return result

    return cast(F, wrapper)