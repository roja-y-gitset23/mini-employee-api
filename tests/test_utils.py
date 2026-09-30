import asyncio

import pytest

from employee_api.utils.decorators import log_execution


def test_log_execution_sync_returns_value_and_preserves_metadata():
    @log_execution
    def add(a, b):
        """Adds."""
        return a + b

    assert add(1, 2) == 3
    assert add.__name__ == "add"
    assert add.__doc__ == "Adds."


def test_log_execution_sync_reraises():
    @log_execution
    def boom():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        boom()


def test_log_execution_async():
    @log_execution
    async def double(x):
        return x * 2

    assert asyncio.run(double(4)) == 8


def test_log_execution_async_reraises():
    @log_execution
    async def boom():
        raise RuntimeError("bad")

    with pytest.raises(RuntimeError):
        asyncio.run(boom())