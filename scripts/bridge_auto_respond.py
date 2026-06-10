#!/usr/bin/env python3
"""Auto-bridge responder: generates canned responses for all request types.

Provides the generic bridge mechanics — request-file polling, JSON read/write,
response envelopes, and request classification. The *content* of each response
comes from a template pack:

  - By default a neutral set of demo templates is used.
  - Pass ``--templates <path-or-module>`` to load an application-specific pack
    (e.g. ``examples/intel_analyzer_bridge/templates.py``).

A template pack is any Python module that defines a subset of:
  PACK_NAME            str  — display name
  TOPIC_PATTERNS       iterable of (topic, [keyword, ...]) checked in order
  STRATEGY_TEMPLATES   dict[topic, strategy text]
  DEFAULT_STRATEGY     str  — fallback strategy text
  EXECUTOR_TEMPLATE    str  — .format()-ed with {strategy_name} and {topic}
  COMPARATOR_RESPONSE  str
  PATCHER_RESPONSE     str
  AUDITOR_RESPONSE     str

Usage:
  python scripts/bridge_auto_respond.py                       # neutral pack, loop
  python scripts/bridge_auto_respond.py --once                # process pending, exit
  python scripts/bridge_auto_respond.py --templates pack.py   # custom pack
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

BRIDGE_DIR = Path("/tmp/skill-evolution-bridge")
REQUEST_DIR = BRIDGE_DIR / "requests"
RESPONSE_DIR = BRIDGE_DIR / "responses"

IDLE_LIMIT = 60  # polling rounds without requests before exiting (~180s)
IDLE_SLEEP = 3  # seconds between polls when idle
BUSY_SLEEP = 2  # seconds between polls after processing


# ── Generic bridge mechanics ─────────────────────────────────────────────────


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
    system = data.get("system", "")
    sl = system.lower()
    # Also check user message for format hints
    msgs = data.get("messages", [{}])
    user_msg = (msgs[0].get("content", "") if msgs else "").lower()

    # IMPORTANT: check patcher BEFORE comparator — both mention "delta signals"
    # but patcher also mentions "patch" or "precision skill editor"
    if ("skill_patch" in sl
            or "precision skill editor" in sl
            or ("patch" in sl and "delta signal" in sl)
            or "===updated_body===" in sl):
        return "patcher"
    elif ("strategy diversification engine" in sl
            or "strategy diversification expert" in sl
            or "strategy generation" in sl
            or "===strategy" in sl
            or ("generate exactly" in user_msg and "diverse strategies" in user_msg)):
        return "strategy_generation"
    elif "you are an ai agent executing a task" in sl or "execution trace" in sl:
        return "executor"
    elif ("trajectory comparison" in sl
          or ("compare" in sl and "trajectory" in sl)
          or "skill improvement analyst" in sl
          or ("delta signal" in sl and "patch" not in sl)):
        return "comparator"
    elif "audit" in sl and ("skill" in sl or "review" in sl):
        return "auditor"
    else:
        return "unknown"


def extract_task_topic(data: dict, topic_patterns=()) -> str:
    """Classify the user message into a topic via keyword patterns.

    ``topic_patterns`` is an ordered iterable of ``(topic, keywords)`` pairs;
    the first topic whose keywords match (case-insensitive substring) wins.
    Returns "general" when nothing matches (or no patterns are configured).
    """
    msgs = data.get("messages", [{}])
    content = (msgs[0].get("content", "") if msgs else "").lower()
    for topic, keywords in topic_patterns:
        if any(keyword.lower() in content for keyword in keywords):
            return topic
    return "general"


def extract_strategy_name(data: dict) -> str:
    """Extract strategy name from executor system prompt."""
    system = data.get("system", "")
    m = re.search(r"## Strategy to Follow\n(.+?)(?:\n[0-9]\.|\n\n)", system)
    return m.group(1).strip() if m else "unknown"


# ── Neutral demo templates (defaults) ────────────────────────────────────────

DEFAULT_STRATEGY = """===STRATEGY 1===
Name: Systematic Rule Enhancement
Description: Analyze the failure mode root cause and add explicit rules with tunable thresholds.
Approach:
Analyze the specific failure mode described in the task. Identify the root cause in the current skill's
processing pipeline. Add explicit rules and checks at the appropriate pipeline stage to address the gap.
Include concrete thresholds and parameters that can be tuned based on feedback.

===STRATEGY 2===
Name: LLM-Assisted Classification
Description: Add a classification step before the affected pipeline stage with confidence thresholds.
Approach:
Use the existing LLM dependency to add a classification step before the affected pipeline stage.
Prompt the LLM with specific criteria for the problem domain. Apply the classification result to modify
scoring, filtering, or output generation. Include confidence thresholds and fallback behavior.

===STRATEGY 3===
Name: Data-Driven Adaptive Approach
Description: Derive adaptive thresholds from pipeline output statistics for self-improving behavior over time.
Approach:
Collect statistics from the current pipeline output to characterize the problem quantitatively. Use these
statistics to derive adaptive thresholds that respond to the specific data distribution. Implement feedback
mechanisms so the approach improves over time as more data flows through the pipeline."""

EXECUTOR_TEMPLATE = """## Execution Trace: {strategy_name}

### Step 1: Analyze Current Skill and Task Requirements

The task requires addressing: {topic}
Strategy being applied: {strategy_name}

After reading the current skill document, I identify the relevant pipeline stage and the specific gap
this strategy addresses.

### Step 2: Implementation

Following the strategy step by step:

1. **Pre-processing**: Parse the current skill's pipeline stages to identify where the modification fits.

2. **Core logic implementation**: Apply the {strategy_name} approach as specified in the strategy document:
   - Add new classification/scoring/filtering logic at the appropriate pipeline stage
   - Define concrete thresholds and parameters based on the problem analysis
   - Implement validation checks to prevent regression on existing functionality

3. **Integration**: The new logic integrates with the existing pipeline, ensuring upstream data is
   available and downstream consumers receive properly formatted output.

### Step 3: Validation

Applied the modified pipeline to the evaluation dataset:

**Before (current skill):** the failure mode described in the task is present.
**After (with strategy applied):** problem items are correctly handled, with no regression on
previously correct items, and output format stays compatible with downstream consumers.

### Step 4: Output

The modified skill section has been updated with:
- New processing rules specific to {topic}
- Concrete parameters and thresholds from the {strategy_name} strategy
- Documentation of the decision logic for transparency"""

COMPARATOR_RESPONSE = """===SIGNAL 1===
Category: missing_knowledge
Affects: body
Confidence: 0.75
Description: The skill lacks explicit guidance for the failure mode observed in the failed trajectory.
Evidence: The successful trajectory verified its output before finishing; the failed trajectory skipped that step.

===SIGNAL 2===
Category: edge_case
Affects: body
Confidence: 0.65
Description: Boundary inputs are not addressed by the current skill instructions.
Evidence: The failed trajectory mishandled an input at the edge of the expected range; the successful one did not.

===END==="""

PATCHER_RESPONSE = """===UPDATED_BODY===
# Demo Skill

This is a neutral demonstration patch produced by the generic bridge responder.

1. Validate all inputs before processing.
2. Handle errors explicitly at every step.
3. Verify outputs against the task requirements before finishing.

===CHANGELOG===
1. Added explicit input validation guidance
2. Added error handling and output verification steps"""

AUDITOR_RESPONSE = """===CHECK: structural_integrity===
Severity: PASS
Description: Required sections are present and well-formed.
Suggestion: None needed.

===CHECK: logical_consistency===
Severity: PASS
Description: Instructions do not contradict each other.
Suggestion: None needed.

===OVERALL===
Severity: PASS
Summary: Demo audit from the generic bridge responder; no blocking issues found."""


# ── Template packs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TemplatePack:
    """Bundle of response templates the responder uses for each request type."""

    name: str = "neutral-demo"
    topic_patterns: tuple[tuple[str, tuple[str, ...]], ...] = ()
    strategy_templates: dict[str, str] = field(default_factory=dict)
    default_strategy: str = DEFAULT_STRATEGY
    executor_template: str = EXECUTOR_TEMPLATE
    comparator_response: str = COMPARATOR_RESPONSE
    patcher_response: str = PATCHER_RESPONSE
    auditor_response: str = AUDITOR_RESPONSE

    @classmethod
    def from_module(cls, module) -> "TemplatePack":
        """Build a pack from a template module, falling back to neutral defaults."""
        base = cls()
        return cls(
            name=getattr(module, "PACK_NAME", getattr(module, "__name__", "custom")),
            topic_patterns=tuple(
                (topic, tuple(keywords))
                for topic, keywords in getattr(module, "TOPIC_PATTERNS", ())
            ),
            strategy_templates=dict(getattr(module, "STRATEGY_TEMPLATES", {})),
            default_strategy=getattr(module, "DEFAULT_STRATEGY", base.default_strategy),
            executor_template=getattr(module, "EXECUTOR_TEMPLATE", base.executor_template),
            comparator_response=getattr(module, "COMPARATOR_RESPONSE", base.comparator_response),
            patcher_response=getattr(module, "PATCHER_RESPONSE", base.patcher_response),
            auditor_response=getattr(module, "AUDITOR_RESPONSE", base.auditor_response),
        )


def load_templates(spec: str | None) -> TemplatePack:
    """Load a template pack from a file path or importable module name.

    ``spec=None`` returns the neutral built-in pack.
    """
    if not spec:
        return TemplatePack()

    path = Path(spec)
    if path.suffix == ".py":
        if not path.exists():
            raise FileNotFoundError(f"Template pack not found: {spec}")
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"Cannot load template pack from: {spec}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(spec)
    return TemplatePack.from_module(module)


# ── Response generators ──────────────────────────────────────────────────────


def generate_strategy_response(data: dict, pack: TemplatePack) -> str:
    topic = extract_task_topic(data, pack.topic_patterns)
    return pack.strategy_templates.get(topic, pack.default_strategy)


def generate_executor_response(data: dict, pack: TemplatePack) -> str:
    return pack.executor_template.format(
        strategy_name=extract_strategy_name(data),
        topic=extract_task_topic(data, pack.topic_patterns),
    )


def generate_comparator_response(data: dict, pack: TemplatePack) -> str:
    return pack.comparator_response


def generate_patcher_response(data: dict, pack: TemplatePack) -> str:
    return pack.patcher_response


def generate_auditor_response(data: dict, pack: TemplatePack) -> str:
    return pack.auditor_response


RESPONSE_GENERATORS = {
    "strategy_generation": generate_strategy_response,
    "executor": generate_executor_response,
    "comparator": generate_comparator_response,
    "patcher": generate_patcher_response,
    "auditor": generate_auditor_response,
}


# ── CLI ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-respond to pending skill-evolution bridge requests."
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process all pending requests once, then exit.",
    )
    parser.add_argument(
        "--templates", default=None, metavar="PATH_OR_MODULE",
        help="Template pack: a .py file path or an importable module name. "
             "Defaults to neutral built-in demo templates.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = _parse_args(argv)
    try:
        pack = load_templates(args.templates)
    except (FileNotFoundError, ImportError) as exc:
        print(f"[Bridge Auto] Failed to load templates: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    setup()

    idle_count = 0
    processed = 0

    # Write a ready sentinel so the pipeline knows we're active
    ready_file = BRIDGE_DIR / ".ready"
    ready_file.write_text(str(int(time.time())), encoding="utf-8")

    print(f"[Bridge Auto] Started (templates: {pack.name}) — processing requests...")

    while True:
        pending = list_pending()

        if not pending:
            idle_count += 1
            if idle_count > IDLE_LIMIT:
                print(
                    f"[Bridge Auto] No requests for {IDLE_LIMIT * IDLE_SLEEP}s — "
                    f"stopping. Processed {processed} total."
                )
                break
            time.sleep(IDLE_SLEEP)
            continue

        idle_count = 0

        for req in pending:
            req_id = req["id"]
            req_type = classify_request(req)
            topic = extract_task_topic(req, pack.topic_patterns)

            generator = RESPONSE_GENERATORS.get(req_type)
            if generator:
                content = generator(req, pack)
                write_response(req_id, content)
                processed += 1
                print(f"[Bridge Auto] ✓ {req_id[:8]}... type={req_type} topic={topic} — responded")
            else:
                # Unknown type — write generic response
                write_response(req_id, f"Processed request of type: {req_type}")
                processed += 1
                print(f"[Bridge Auto] ? {req_id[:8]}... type={req_type} — generic response")

        if args.once:
            break

        time.sleep(BUSY_SLEEP)


if __name__ == "__main__":
    main()
