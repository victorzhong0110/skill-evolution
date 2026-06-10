# intel_analyzer_bridge — historical example template pack

Canned bridge responses used during early development to evolve the
`intel-analyzer` skill (a bilingual AI-news scoring pipeline). The topics,
entities (TeraWulf, EngineAI, SpaceX, ...), and scoring formulas in
`templates.py` are specific to that application — they are an example, not
part of the generic framework.

The generic responder lives in `scripts/bridge_auto_respond.py` and ships
with neutral demo templates. Load this pack to reproduce the original
intel-analyzer behavior:

```bash
python scripts/bridge_auto_respond.py --templates examples/intel_analyzer_bridge/templates.py
```

A template pack is any Python module defining a subset of: `PACK_NAME`,
`TOPIC_PATTERNS`, `STRATEGY_TEMPLATES`, `DEFAULT_STRATEGY`,
`EXECUTOR_TEMPLATE`, `COMPARATOR_RESPONSE`, `PATCHER_RESPONSE`,
`AUDITOR_RESPONSE`. Missing attributes fall back to the neutral defaults.
