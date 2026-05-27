#!/usr/bin/env python3
"""Bridge monitor helper — lists pending requests for a Claude Code session to process.

This script is NOT the monitor itself. It's a utility that:
  1. Lists pending requests in the bridge directory
  2. Shows request details (system prompt preview, user prompt preview)
  3. Can be called by a Claude Code session to discover what needs processing

The actual monitoring loop runs inside the Claude Code session, which:
  1. Calls this script to find pending requests
  2. Spawns Agent sub-tasks to process each request
  3. Writes responses back to the bridge directory

Usage:
  python scripts/bridge_monitor.py list          # List pending requests
  python scripts/bridge_monitor.py read <id>     # Read full request details
  python scripts/bridge_monitor.py respond <id>  # Write response (from stdin)
  python scripts/bridge_monitor.py clean         # Remove stale request/response files
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BRIDGE_DIR = Path("/tmp/skill-evolution-bridge")
REQUEST_DIR = BRIDGE_DIR / "requests"
RESPONSE_DIR = BRIDGE_DIR / "responses"


def setup():
    """Ensure bridge directories exist."""
    REQUEST_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)


def list_pending() -> list[dict]:
    """List all pending requests (no matching response yet)."""
    setup()
    pending = []
    for req_file in sorted(REQUEST_DIR.glob("*.json")):
        request_id = req_file.stem
        resp_file = RESPONSE_DIR / f"{request_id}.json"
        if not resp_file.exists():
            try:
                data = json.loads(req_file.read_text(encoding="utf-8"))
                system_preview = data.get("system", "")[:100]
                messages = data.get("messages", [])
                prompt_preview = messages[-1]["content"][:100] if messages else ""
                pending.append({
                    "id": request_id,
                    "system_preview": system_preview,
                    "prompt_preview": prompt_preview,
                    "model": data.get("model", "unknown"),
                    "age_seconds": time.time() - req_file.stat().st_mtime,
                })
            except (json.JSONDecodeError, KeyError):
                pending.append({"id": request_id, "error": "malformed request"})
    return pending


def read_request(request_id: str) -> dict | None:
    """Read full request data."""
    req_file = REQUEST_DIR / f"{request_id}.json"
    if not req_file.exists():
        return None
    return json.loads(req_file.read_text(encoding="utf-8"))


def write_response(request_id: str, content: str) -> None:
    """Write a response for a request."""
    setup()
    response_data = {
        "content": content,
        "model": "bridge-agent",
        "input_tokens": 0,
        "output_tokens": 0,
        "stop_reason": "end_turn",
    }
    resp_file = RESPONSE_DIR / f"{request_id}.json"
    tmp_file = resp_file.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(response_data, ensure_ascii=False), encoding="utf-8")
    tmp_file.rename(resp_file)


def clean_stale(max_age_seconds: int = 600) -> int:
    """Remove request/response files older than max_age_seconds."""
    setup()
    removed = 0
    for d in [REQUEST_DIR, RESPONSE_DIR]:
        for f in d.glob("*.json"):
            if time.time() - f.stat().st_mtime > max_age_seconds:
                f.unlink(missing_ok=True)
                removed += 1
    return removed


def main():
    if len(sys.argv) < 2:
        print("Usage: bridge_monitor.py <list|read|respond|clean>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        pending = list_pending()
        if not pending:
            print("NO_PENDING")
        else:
            print(json.dumps(pending, indent=2, ensure_ascii=False))

    elif cmd == "read":
        if len(sys.argv) < 3:
            print("Usage: bridge_monitor.py read <request_id>")
            sys.exit(1)
        data = read_request(sys.argv[2])
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("NOT_FOUND")
            sys.exit(1)

    elif cmd == "respond":
        if len(sys.argv) < 3:
            print("Usage: bridge_monitor.py respond <request_id>")
            sys.exit(1)
        content = sys.stdin.read()
        write_response(sys.argv[2], content)
        print("OK")

    elif cmd == "clean":
        removed = clean_stale()
        print(f"Removed {removed} stale files")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
