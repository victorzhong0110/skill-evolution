"""Bounded retry / timeout helpers for HTTP LLM clients."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from skill_evolution.llm.claude_backend import ClaudeBackend
from skill_evolution.llm.http_retry import (
    MAX_RETRIES_CAP,
    call_with_retry,
    clamp_max_retries,
    is_retryable,
    retry_after_seconds,
    retry_delay,
)
from skill_evolution.llm.openai_backend import OpenAIBackend


class _StatusError(Exception):
    def __init__(self, status_code: int, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers or {})


class TestIsRetryable:
    def test_timeout_error(self):
        assert is_retryable(TimeoutError("slow"))

    def test_connection_error(self):
        assert is_retryable(ConnectionError("reset"))

    def test_429(self):
        assert is_retryable(_StatusError(429))

    def test_503(self):
        assert is_retryable(_StatusError(503))

    def test_529_overloaded(self):
        assert is_retryable(_StatusError(529))

    def test_400_not_retryable(self):
        assert not is_retryable(_StatusError(400))

    def test_401_not_retryable(self):
        assert not is_retryable(_StatusError(401))

    def test_named_rate_limit(self):
        class RateLimitError(Exception):
            pass

        assert is_retryable(RateLimitError("slow down"))

    def test_named_timeout(self):
        class APITimeoutError(Exception):
            pass

        assert is_retryable(APITimeoutError("deadline"))

    def test_generic_value_error_not_retryable(self):
        assert not is_retryable(ValueError("bad json"))


class TestRetryDelay:
    def test_exponential(self):
        exc = _StatusError(503)
        assert retry_delay(exc, 0, 0.5) == 0.5
        assert retry_delay(exc, 1, 0.5) == 1.0
        assert retry_delay(exc, 2, 0.5) == 2.0

    def test_capped(self):
        exc = _StatusError(503)
        assert retry_delay(exc, 8, 0.5, max_backoff_s=8.0) == 8.0

    def test_retry_after_honored_and_capped(self):
        exc = _StatusError(429, headers={"retry-after": "2.5"})
        assert retry_after_seconds(exc) == 2.5
        assert retry_delay(exc, 0, 0.5, max_backoff_s=8.0) == 2.5
        long = _StatusError(429, headers={"Retry-After": "99"})
        assert retry_delay(long, 0, 0.5, max_backoff_s=8.0) == 8.0


class TestClamp:
    def test_cap(self):
        assert clamp_max_retries(99) == MAX_RETRIES_CAP
        assert clamp_max_retries(-3) == 0
        assert clamp_max_retries(3) == 3


class TestCallWithRetry:
    async def test_succeeds_first_try(self):
        async def ok():
            return "ok"

        assert await call_with_retry(ok, max_retries=3, backoff_s=0) == "ok"

    async def test_retries_429_then_succeeds(self):
        n = {"calls": 0}
        slept: list[float] = []

        async def flaky():
            n["calls"] += 1
            if n["calls"] < 3:
                raise _StatusError(429)
            return "done"

        async def fake_sleep(delay: float):
            slept.append(delay)

        result = await call_with_retry(
            flaky, max_retries=3, backoff_s=0.5, sleep=fake_sleep
        )
        assert result == "done"
        assert n["calls"] == 3
        assert slept == [0.5, 1.0]

    async def test_gives_up_after_bound(self):
        n = {"calls": 0}

        async def always_5xx():
            n["calls"] += 1
            raise _StatusError(503)

        async def fake_sleep(_delay: float):
            return None

        with pytest.raises(_StatusError, match="503"):
            await call_with_retry(
                always_5xx, max_retries=2, backoff_s=0, sleep=fake_sleep
            )
        assert n["calls"] == 3  # first + 2 retries

    async def test_no_retry_on_4xx(self):
        n = {"calls": 0}

        async def bad_request():
            n["calls"] += 1
            raise _StatusError(400)

        with pytest.raises(_StatusError, match="400"):
            await call_with_retry(bad_request, max_retries=5, backoff_s=0)
        assert n["calls"] == 1

    async def test_max_retries_zero_is_single_attempt(self):
        n = {"calls": 0}

        async def boom():
            n["calls"] += 1
            raise _StatusError(429)

        with pytest.raises(_StatusError):
            await call_with_retry(boom, max_retries=0, backoff_s=0)
        assert n["calls"] == 1

    async def test_retries_timeout(self):
        n = {"calls": 0}

        async def slow():
            n["calls"] += 1
            if n["calls"] == 1:
                raise TimeoutError("deadline")
            return "ok"

        async def fake_sleep(_delay: float):
            return None

        assert await call_with_retry(slow, max_retries=1, backoff_s=0, sleep=fake_sleep) == "ok"
        assert n["calls"] == 2


class TestOpenAIBackendRetry:
    def _backend(self, monkeypatch, **kwargs):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        for key in (
            "ALL_PROXY",
            "all_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
        ):
            monkeypatch.delenv(key, raising=False)
        return OpenAIBackend(retry_backoff_s=0, **kwargs)

    async def test_complete_retries_then_records_once(self, monkeypatch):
        backend = self._backend(monkeypatch, max_retries=2)
        n = {"calls": 0}

        async def flaky(**_kwargs):
            n["calls"] += 1
            if n["calls"] < 2:
                raise _StatusError(503)
            choice = SimpleNamespace(
                message=SimpleNamespace(content="hello"),
                finish_reason="stop",
            )
            usage = SimpleNamespace(prompt_tokens=4, completion_tokens=2)
            return SimpleNamespace(choices=[choice], usage=usage)

        backend.client.chat.completions.create = flaky
        resp = await backend.complete("sys", [{"role": "user", "content": "hi"}])
        assert resp.content == "hello"
        assert n["calls"] == 2
        assert backend.usage.calls == 1
        assert backend.usage.total_input == 4

    async def test_complete_does_not_retry_client_error(self, monkeypatch):
        backend = self._backend(monkeypatch, max_retries=3)
        n = {"calls": 0}

        async def bad(**_kwargs):
            n["calls"] += 1
            raise _StatusError(400)

        backend.client.chat.completions.create = bad
        with pytest.raises(_StatusError):
            await backend.complete("", [{"role": "user", "content": "hi"}])
        assert n["calls"] == 1
        assert backend.usage.calls == 0


class TestClaudeBackendRetry:
    def _backend(self, monkeypatch, **kwargs):
        for key in (
            "ALL_PROXY",
            "all_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
        ):
            monkeypatch.delenv(key, raising=False)
        return ClaudeBackend(api_key="sk-ant-test", retry_backoff_s=0, **kwargs)

    async def test_complete_retries_then_records_once(self, monkeypatch):
        backend = self._backend(monkeypatch, max_retries=2)
        n = {"calls": 0}

        async def flaky(**_kwargs):
            n["calls"] += 1
            if n["calls"] < 2:
                raise _StatusError(429)
            block = SimpleNamespace(text="bonjour")
            usage = SimpleNamespace(input_tokens=3, output_tokens=5)
            return SimpleNamespace(
                content=[block],
                usage=usage,
                stop_reason="end_turn",
            )

        backend.client.messages.create = flaky
        resp = await backend.complete("sys", [{"role": "user", "content": "hi"}])
        assert resp.content == "bonjour"
        assert n["calls"] == 2
        assert backend.usage.calls == 1
        assert backend.usage.total_output == 5
