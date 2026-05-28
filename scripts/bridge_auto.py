#!/usr/bin/env python3
"""Auto-bridge: reads pending requests and writes placeholder responses.

For requests that are executor tasks (system starts with "You are an AI agent"),
generates a reasonable task execution response based on the strategy and task.

For other requests (comparator, patcher, auditor), generates appropriate responses
following the expected output format.

Usage:
  python scripts/bridge_auto.py           # Process all pending, loop until idle
  python scripts/bridge_auto.py --once    # Process all pending, exit
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

BRIDGE_DIR = Path("/tmp/skill-evolution-bridge")
REQUEST_DIR = BRIDGE_DIR / "requests"
RESPONSE_DIR = BRIDGE_DIR / "responses"


def setup():
    REQUEST_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSE_DIR.mkdir(parents=True, exist_ok=True)


def list_pending() -> list[dict]:
    setup()
    pending = []
    for req_file in sorted(REQUEST_DIR.glob("*.json")):
        request_id = req_file.stem
        resp_file = RESPONSE_DIR / f"{request_id}.json"
        if not resp_file.exists():
            try:
                data = json.loads(req_file.read_text(encoding="utf-8"))
                pending.append(data)
            except (json.JSONDecodeError, KeyError):
                pass
    return pending


def write_response(request_id: str, content: str):
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


def classify_request(data: dict) -> str:
    """Classify request type based on system prompt content."""
    system = data.get("system", "")
    if "strategy diversification engine" in system.lower() or "strategy generation" in system.lower():
        return "strategy_generation"
    elif "you are an ai agent executing a task" in system.lower():
        return "executor"
    elif "trajectory comparison" in system.lower() or "compare" in system.lower() and "trajectory" in system.lower():
        return "comparator"
    elif "skill_patch" in system.lower() or "patch" in system.lower() and "delta signal" in system.lower():
        return "patcher"
    elif "audit" in system.lower() and ("skill" in system.lower() or "review" in system.lower()):
        return "auditor"
    else:
        return "unknown"


def main():
    once = "--once" in sys.argv
    setup()

    idle_count = 0
    processed = 0

    print("[Bridge Auto] Started — waiting for requests...")

    while True:
        pending = list_pending()

        if not pending:
            idle_count += 1
            if idle_count > 20:  # 60 seconds of no requests
                print(f"[Bridge Auto] No requests for 60s — stopping. Processed {processed} total.")
                break
            time.sleep(3)
            continue

        idle_count = 0

        for req in pending:
            req_id = req["id"]
            req_type = classify_request(req)
            system_len = len(req.get("system", ""))
            user_content = req.get("messages", [{}])[0].get("content", "")
            user_len = len(user_content)

            print(f"[Bridge Auto] {req_id[:8]}... type={req_type} (sys={system_len}, usr={user_len})")
            print(f"  → Needs Agent processing. Skipping (use bridge_monitor.py for manual processing).")

        if once:
            break

        time.sleep(3)


if __name__ == "__main__":
    main()
