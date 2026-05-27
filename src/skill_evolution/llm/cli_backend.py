"""Claude Code CLI backend — uses the local `claude` CLI for LLM calls.

No API key required. Leverages the user's existing Claude Code
authentication (OAuth/subscription). Each call spawns a subprocess
with `claude -p --output-format json`.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from shutil import which

from skill_evolution.llm.base import LLMBackend, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"


class CliLLMBackend(LLMBackend):
    """LLM backend that shells out to the local `claude` CLI."""

    def __init__(self, model: str = _DEFAULT_MODEL, claude_bin: str | None = None):
        super().__init__(model=model)
        self.model = model
        self._bin = claude_bin or which("claude") or "claude"

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Run a single-turn completion via `claude -p`.

        Uses a temp file for the system prompt to avoid shell escaping
        issues with long or complex prompts.
        """
        prompt = messages[-1]["content"] if messages else ""

        cmd = [
            self._bin,
            "-p",
            "--model", self.model,
            "--output-format", "json",
        ]

        system_file = None
        try:
            if system:
                system_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8",
                )
                system_file.write(system)
                system_file.close()
                cmd.extend(["--system-prompt-file", system_file.name])

            logger.debug(
                "CLI LLM call: model=%s, prompt_len=%d, system_len=%d",
                self.model, len(prompt), len(system),
            )

            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
            )
        finally:
            if system_file:
                Path(system_file.name).unlink(missing_ok=True)

        if proc.returncode != 0:
            error_detail = proc.stderr[:500] or proc.stdout[:500]
            raise RuntimeError(
                f"claude CLI failed (exit {proc.returncode}): {error_detail}"
            )

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse claude CLI JSON output: {exc}\n"
                f"stdout: {proc.stdout[:500]}"
            ) from exc

        if data.get("is_error"):
            raise RuntimeError(f"claude CLI returned error: {data.get('result', 'unknown')}")

        content = data.get("result", "")
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        resp = LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            stop_reason=data.get("stop_reason", ""),
        )
        self.usage.record(resp)
        return resp
