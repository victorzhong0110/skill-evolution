# TODOS

## Core Pipeline

### LLM pricing hardcoded in base.py

**What:** Move LLM model pricing out of hardcoded dictionaries in `llm/base.py:31-32` into a configuration file or make pricing optional.

**Why:** Model pricing changes frequently. Hardcoded values silently become inaccurate, and adding new model support requires code changes. This is a maintenance burden for an open-source tool.

**Context:** `base.py` has `INPUT_PRICING` and `OUTPUT_PRICING` dicts with per-model dollar amounts. Options: (a) move to a YAML/JSON config file, (b) fetch from an API, or (c) make pricing optional with a "pricing unavailable" fallback. Option (c) is simplest for v1.

**Effort:** S
**Priority:** P3
**Depends on:** None

## Meta-Skill Evolution

No open items.

## Completed

### Phase 0: Bug Fixes (T1, T2, T2-ext, T3)

Replaced self-assessment with external TaskEvaluator protocol, fixed {k} placeholder, added deep-copy + audit rollback.

### Phase 1: Test Suite Infrastructure (T7a, T7b, T7c)

Added EvalCase/ScoreResult models with JSONL serialization, test suite loader, and structural scoring functions for strategy_generation and trajectory_comparison meta-skills. Each suite has 6 test cases including adversarial and edge cases. Scoring uses deterministic metrics (v1) to avoid evaluation circularity.

### Phase 2: Snapshot + Regression Gate (T8)

Extended SkillVersionManager with per-version score maps. Added RegressionGate (check_regression) that blocks promotion when any test score drops below baseline, with configurable tolerance.

### Phase 3: Evolution Cycle (T9)

MetaSkillEvolver orchestrator with full cycle: snapshot → baseline score → evolve → candidate score → regression gate → accept/rollback. CLI commands: meta-evolve, meta-test, meta-snapshot. Supports --dry-run, --tolerance, custom test suites, and workspace overrides.

### Cleanup Batch (T4, T5, T10, T12, T13)

DRY prompt deduplication, logger.warning for malformed YAML, doctor CLI command, structured changelog, score trend display.

### Integration Tests + Rich Output (T6, T11)

24 pipeline integration tests with MockLLM. Coverage 36%→81%. Rich score comparison table in MetaSkillEvolver.

### Bug Fixes: Comparator Empty Crash + Auditor Default-to-PASS

Comparator.compare() now returns empty list on empty trajectories. Auditor._parse_report() defaults to FAIL (not PASS) on unparseable output, WARNING when checks exist but no ===OVERALL=== block.

### Investigations Resolved (Evaluation Circularity, T7c Scoring)

V1 uses purely structural/deterministic scoring (format compliance, count accuracy, Jaccard diversity) — avoids evaluation circularity entirely. LLM-as-judge can be added as a v2 enhancement.
