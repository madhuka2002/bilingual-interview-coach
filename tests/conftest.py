"""Shared pytest configuration."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run asynchronous HTTP tests with Python's built-in asyncio backend."""
    return "asyncio"
