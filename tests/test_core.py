import asyncio
import errno
import logging
from unittest.mock import patch

import aiohttp
import pytest
from aiohttp import (
    ClientConnectorDNSError,
    ClientConnectorError,
    ClientConnectorSSLError,
)
from aioresponses import aioresponses

from src.monitor import Monitor, check_url


class MockConnKey:
    def __init__(self):
        self.host = "example.com"
        self.port = 80
        self.ssl = False


@pytest.mark.asyncio
async def test_check_url_success():
    url = "http://ok.com"
    with aioresponses() as m:
        m.get(url, status=200)
        async with aiohttp.ClientSession() as session:
            is_up, message = await check_url(
                session, url, asyncio.Semaphore(1), 1
            )
            assert is_up is True
            assert "OK (200)" in message


@pytest.mark.asyncio
async def test_check_url_dns_error():
    url = "http://bad-dns.test"
    os_err = OSError(errno.ENOENT, "DNS failure")
    exc = ClientConnectorDNSError(MockConnKey(), os_err)

    with aioresponses() as m:
        m.get(url, exception=exc)
        async with aiohttp.ClientSession() as session:
            is_up, message = await check_url(
                session, url, asyncio.Semaphore(1), 1
            )
            assert is_up is False
            assert "DNS Error" in message


@pytest.mark.asyncio
async def test_check_url_connection_refused():
    url = "http://refused.com"
    os_err = OSError(errno.ECONNREFUSED, "Refused")
    exc = ClientConnectorError(MockConnKey(), os_err)

    with aioresponses() as m:
        m.get(url, exception=exc)
        async with aiohttp.ClientSession() as session:
            is_up, message = await check_url(
                session, url, asyncio.Semaphore(1), 1
            )
            assert is_up is False
            assert "Connection refused" in message


@pytest.mark.asyncio
async def test_check_url_ssl_retry_fails():
    url = "https://total-fail.com"
    os_err = OSError(errno.EIO, "SSL fail")
    exc = ClientConnectorSSLError(MockConnKey(), os_err)

    with aioresponses() as m:
        m.get(url, exception=exc)
        m.get(url, exception=Exception("Dead"))

        async with aiohttp.ClientSession() as session:
            is_up, message = await check_url(
                session, url, asyncio.Semaphore(1), 1
            )
            assert is_up is False
            assert "SSL Error" in message


@pytest.mark.asyncio
async def test_check_url_timeout():
    url = "http://slow.com"
    with aioresponses() as m:
        m.get(url, exception=asyncio.TimeoutError())
        async with aiohttp.ClientSession() as session:
            is_up, message = await check_url(
                session, url, asyncio.Semaphore(1), 1
            )
            assert is_up is False
            assert "Timeout" in message


@pytest.mark.asyncio
async def test_check_url_generic_exception():
    url = "http://crash.com"
    with aioresponses() as m:
        m.get(url, exception=RuntimeError("Crash"))
        async with aiohttp.ClientSession() as session:
            is_up, message = await check_url(
                session, url, asyncio.Semaphore(1), 1
            )
            assert is_up is False
            assert "Unexpected: RuntimeError" in message


@pytest.mark.asyncio
async def test_monitor_worker_lifecycle(caplog):
    caplog.set_level(logging.INFO)
    url = "http://test-site.com"
    monitor = Monitor([url], interval=0.1, timeout=1, max_req=1)

    side_effects = [
        (True, "OK (200)"),
        (False, "HTTP 500"),
        (True, "OK (200)"),
    ]

    async def mock_check(*args, **kwargs):
        if not side_effects:
            raise asyncio.CancelledError()
        return side_effects.pop(0)

    with (
        patch("src.monitor.core.check_url", side_effect=mock_check),
        patch("asyncio.sleep", return_value=None),
    ):
        async with aiohttp.ClientSession() as session:
            with pytest.raises(asyncio.CancelledError):
                await monitor._worker(session, url)

    assert "STARTUP: http://test-site.com is UP" in caplog.text
    assert "FAILURE: http://test-site.com is now OFFLINE" in caplog.text
    assert "RECOVERY: http://test-site.com is back ONLINE" in caplog.text


@pytest.mark.asyncio
async def test_monitor_run_full_cycle():
    monitor = Monitor(["http://test.com"], 1, 1, 1)
    with (
        patch("aiohttp.ClientSession.get"),
        patch(
            "src.monitor.core.Monitor._worker",
            side_effect=asyncio.CancelledError,
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await monitor.run()
