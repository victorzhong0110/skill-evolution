"""Tests for the file-bridge and CLI backends — the two I/O-heavy backends.

BridgeBackend is exercised against a real tmp_path bridge directory (the
actual file protocol, including cleanup); CliLLMBackend against a faked
subprocess. No network, no real `claude` binary.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from skill_evolution.llm.bridge_backend import BridgeBackend
from skill_evolution.llm.cli_backend import CliLLMBackend

# ---- BridgeBackend ---------------------------------------------------------


def _bridge(tmp_path, timeout=5):
    return BridgeBackend(model="test-model", bridge_dir=tmp_path, timeout=timeout)


async def _respond_when_requested(backend: BridgeBackend, payload: dict) -> None:
    """Play the monitor's role: wait for the request file, write the response."""
    for _ in range(100):
        requests = list(backend.request_dir.glob("*.json"))
        if requests:
            request_id = requests[0].stem
            data = json.loads(requests[0].read_text(encoding="utf-8"))
            assert data["id"] == request_id  # protocol sanity
            response = backend.response_dir / f"{request_id}.json"
            response.write_text(json.dumps(payload), encoding="utf-8")
            return
        await asyncio.sleep(0.02)
    raise AssertionError("request file never appeared")


async def test_bridge_round_trip(tmp_path):
    backend = _bridge(tmp_path)
    monitor = asyncio.create_task(_respond_when_requested(
        backend, {"content": "hello", "input_tokens": 7, "output_tokens": 3}))
    resp = await backend.complete("sys", [{"role": "user", "content": "hi"}])
    await monitor
    assert resp.content == "hello"
    assert backend.usage.total_input == 7 and backend.usage.total_output == 3
    # protocol files are cleaned up after a successful exchange
    assert not list(backend.request_dir.glob("*.json"))
    assert not list(backend.response_dir.glob("*.json"))


async def test_bridge_timeout_cleans_request(tmp_path):
    backend = _bridge(tmp_path, timeout=0)  # first poll tick exceeds the budget
    with pytest.raises(TimeoutError, match="monitor running"):
        await backend.complete("sys", [{"role": "user", "content": "hi"}])
    assert not list(backend.request_dir.glob("*.json"))  # stale request removed


async def test_bridge_error_response_raises(tmp_path):
    backend = _bridge(tmp_path)
    monitor = asyncio.create_task(_respond_when_requested(
        backend, {"error": "monitor exploded"}))
    with pytest.raises(RuntimeError, match="monitor exploded"):
        await backend.complete("sys", [{"role": "user", "content": "hi"}])
    await monitor


async def test_bridge_corrupt_response_raises_and_cleans(tmp_path):
    backend = _bridge(tmp_path)

    async def corrupt_monitor():
        for _ in range(100):
            requests = list(backend.request_dir.glob("*.json"))
            if requests:
                (backend.response_dir / f"{requests[0].stem}.json").write_text(
                    "{not json", encoding="utf-8")
                return
            await asyncio.sleep(0.02)

    monitor = asyncio.create_task(corrupt_monitor())
    with pytest.raises(RuntimeError, match="Invalid bridge response"):
        await backend.complete("sys", [{"role": "user", "content": "hi"}])
    await monitor
    # cleanup happens even on the failure path
    assert not list(backend.request_dir.glob("*.json"))
    assert not list(backend.response_dir.glob("*.json"))


# ---- CliLLMBackend ---------------------------------------------------------


def _cli_json(result="ok", is_error=False, **extra):
    payload = {
        "result": result,
        "is_error": is_error,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 2},
    }
    payload.update(extra)
    return json.dumps(payload)


def _fake_run(stdout="", returncode=0, stderr="", capture_cmd=None):
    def fake(cmd, **kwargs):
        if capture_cmd is not None:
            capture_cmd.append(cmd)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    return fake


async def test_cli_happy_path_sums_cache_tokens(monkeypatch):
    import skill_evolution.llm.cli_backend as mod
    monkeypatch.setattr(mod.subprocess, "run", _fake_run(stdout=_cli_json("hi")))
    backend = CliLLMBackend(model="test-model", claude_bin="/fake/claude")
    resp = await backend.complete("", [{"role": "user", "content": "q"}])
    assert resp.content == "hi"
    assert resp.input_tokens == 15  # input + cache_read are both real spend
    assert resp.output_tokens == 2


async def test_cli_system_prompt_goes_through_temp_file(monkeypatch):
    import skill_evolution.llm.cli_backend as mod
    seen: list = []
    monkeypatch.setattr(mod.subprocess, "run",
                        _fake_run(stdout=_cli_json(), capture_cmd=seen))
    backend = CliLLMBackend(model="test-model", claude_bin="/fake/claude")
    await backend.complete("be terse", [{"role": "user", "content": "q"}])
    cmd = seen[0]
    assert "--system-prompt-file" in cmd
    system_path = cmd[cmd.index("--system-prompt-file") + 1]
    from pathlib import Path
    assert not Path(system_path).exists()  # temp file cleaned up after the call


async def test_cli_nonzero_exit_raises(monkeypatch):
    import skill_evolution.llm.cli_backend as mod
    monkeypatch.setattr(mod.subprocess, "run",
                        _fake_run(returncode=1, stderr="boom"))
    backend = CliLLMBackend(model="test-model", claude_bin="/fake/claude")
    with pytest.raises(RuntimeError, match="exit 1.*boom"):
        await backend.complete("", [{"role": "user", "content": "q"}])


async def test_cli_bad_json_raises(monkeypatch):
    import skill_evolution.llm.cli_backend as mod
    monkeypatch.setattr(mod.subprocess, "run", _fake_run(stdout="not json"))
    backend = CliLLMBackend(model="test-model", claude_bin="/fake/claude")
    with pytest.raises(RuntimeError, match="parse claude CLI JSON"):
        await backend.complete("", [{"role": "user", "content": "q"}])


async def test_cli_is_error_payload_raises(monkeypatch):
    import skill_evolution.llm.cli_backend as mod
    monkeypatch.setattr(mod.subprocess, "run",
                        _fake_run(stdout=_cli_json("auth failed", is_error=True)))
    backend = CliLLMBackend(model="test-model", claude_bin="/fake/claude")
    with pytest.raises(RuntimeError, match="auth failed"):
        await backend.complete("", [{"role": "user", "content": "q"}])
