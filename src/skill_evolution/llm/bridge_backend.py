"""Session Bridge backend — file-based IPC with a running Claude Code session.

Instead of spawning expensive `claude -p` subprocesses (each with full Claude Code
overhead), this backend writes requests to a bridge directory and waits for a
monitoring Claude Code session to process them via lightweight Agent calls.

Protocol:
  1. Backend writes  <bridge_dir>/requests/<uuid>.json
  2. Monitor (Claude Code session) detects new file, processes via Agent
  3. Monitor writes   <bridge_dir>/responses/<uuid>.json
  4. Backend reads response and returns

Cost savings vs `claude -p`:
  - No Node.js process startup per call
  - No Claude Code system prompt overhead (~3-5K tokens per call)
  - No MCP server initialization per call
  - Shared session authentication
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from skill_evolution.llm.base import LLMBackend, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_BRIDGE_DIR = Path("/tmp/skill-evolution-bridge")
_DEFAULT_TIMEOUT = 300  # seconds
_POLL_INTERVAL = 0.5  # seconds


class BridgeBackend(LLMBackend):
    """LLM backend that communicates with a Claude Code session via file IPC."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        bridge_dir: Path | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        super().__init__(model=model)
        self.model = model
        self.bridge_dir = bridge_dir or _DEFAULT_BRIDGE_DIR
        self.request_dir = self.bridge_dir / "requests"
        self.response_dir = self.bridge_dir / "responses"
        self._timeout = timeout
        self._setup_dirs()

    def _setup_dirs(self) -> None:
        """Create bridge directories if they don't exist."""
        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.response_dir.mkdir(parents=True, exist_ok=True)

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Write a request file and wait for the monitor to produce a response."""
        request_id = str(uuid.uuid4())

        request_data = {
            "id": request_id,
            "system": system,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": self.model,
        }

        request_file = self.request_dir / f"{request_id}.json"
        response_file = self.response_dir / f"{request_id}.json"

        # Write request atomically (write to tmp then rename)
        tmp_file = request_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(request_data, ensure_ascii=False), encoding="utf-8")
        tmp_file.rename(request_file)

        logger.info(
            "Bridge request %s: system_len=%d, prompt_len=%d",
            request_id[:8],
            len(system),
            len(messages[-1]["content"]) if messages else 0,
        )

        # Poll for response
        start = time.monotonic()
        while not response_file.exists():
            elapsed = time.monotonic() - start
            if elapsed > self._timeout:
                # Clean up stale request
                request_file.unlink(missing_ok=True)
                raise TimeoutError(
                    f"Bridge timeout after {self._timeout}s waiting for "
                    f"response to request {request_id[:8]}. "
                    f"Is the Claude Code monitor running?"
                )
            time.sleep(_POLL_INTERVAL)

        # Read response
        try:
            data = json.loads(response_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid bridge response for {request_id[:8]}: {exc}"
            ) from exc
        finally:
            # Clean up both files
            request_file.unlink(missing_ok=True)
            response_file.unlink(missing_ok=True)

        if "error" in data:
            raise RuntimeError(f"Bridge error: {data['error']}")

        content = data.get("content", "")
        resp = LLMResponse(
            content=content,
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            model=self.model,
            stop_reason=data.get("stop_reason", ""),
        )
        self.usage.record(resp)
        return resp
