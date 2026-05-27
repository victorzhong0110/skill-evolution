# TODOS

## Core Pipeline

### Comparator crashes on empty trajectories list

**What:** `comparator.py:compare()` crashes when called with an empty trajectories list — add an early return with an empty signals list.

**Why:** The pipeline can legally produce zero trajectories (e.g., budget exhaustion mid-round, zero tasks provided). An unhandled crash at this point kills the entire evolution run instead of gracefully continuing.

**Context:** `compare()` indexes into the trajectories list without a length check. The fix is a 2-line guard at the top of `compare()` that returns an empty `ComparisonResult`. The test plan already covers this as an edge case ("Zero tasks provided to evolve").

**Effort:** S
**Priority:** P1
**Depends on:** None

### Auditor defaults to PASS on unparseable LLM output

**What:** `auditor.py` defaults to `PASS` when it fails to parse the LLM's audit response — change default to `FAIL` (or `WARNING`) so unparseable output is treated as a failed audit.

**Why:** The auditor is the last safety gate before a patched skill is accepted. If it silently passes on malformed output, a degraded patch can slip through unchallenged. This directly undermines the audit rollback logic (D11) and the regression gate in meta-skill evolution.

**Context:** The `_parse_audit_result()` method has a fallback path that returns `AuditResult(passed=True, ...)` when parsing fails. The fix is to change this fallback to `passed=False` with a clear reason ("unparseable audit output — defaulting to FAIL"). This pairs naturally with the D11 audit rollback implementation.

**Effort:** S
**Priority:** P1
**Depends on:** None

### LLM pricing hardcoded in base.py

**What:** Move LLM model pricing out of hardcoded dictionaries in `llm/base.py:31-32` into a configuration file or make pricing optional.

**Why:** Model pricing changes frequently. Hardcoded values silently become inaccurate, and adding new model support requires code changes. This is a maintenance burden for an open-source tool.

**Context:** `base.py` has `INPUT_PRICING` and `OUTPUT_PRICING` dicts with per-model dollar amounts. Options: (a) move to a YAML/JSON config file, (b) fetch from an API, or (c) make pricing optional with a "pricing unavailable" fallback. Option (c) is simplest for v1.

**Effort:** S
**Priority:** P3
**Depends on:** None

## Meta-Skill Evolution

### Investigation: Evaluation circularity in scoring functions

**What:** If T7c scoring functions use LLM calls to judge meta-skill output quality, the system is still LLM-judging-LLM — the same self-bootstrap paradox the external evaluation approach was designed to solve.

**Why:** The entire meta-skill evolution safety guarantee (regression gate, ground-truth test sets) relies on scoring functions producing reliable scores. If scoring itself is circular, the gate is checking against unreliable baselines.

**Context:** Identified during CEO review (D13). Three approaches to investigate: (a) purely structural/deterministic metrics (e.g., output format compliance, keyword presence, length constraints) — reliable but shallow; (b) LLM-as-judge with a different model than the one being evolved — breaks the self-loop but still has LLM variability; (c) human-annotated ground truth with automated comparison — most reliable but highest upfront cost. The user offered to help with NLP evaluation literature search. This investigation should happen before T7c implementation.

**Effort:** M (human: ~1 day research / CC: ~30min)
**Priority:** P1
**Depends on:** None. Blocks T7c.

### Investigation: T7c scoring function design as research problem

**What:** Natural-language quality evaluation for meta-skill outputs (e.g., "is this strategy generation prompt better than that one?") is a research-level problem, not a 15-minute engineering task. The CEO plan estimates T7c at CC: ~15min which may be severely underestimated.

**Why:** The scoring functions determine whether meta-skill evolution actually improves quality or just changes text. Getting this wrong means the regression gate passes bad changes or blocks good ones.

**Context:** Identified during CEO review (D14). Options: (a) start with simple structural metrics (format compliance, placeholder presence, output length) as v1 scoring — fast to implement, limited signal; (b) invest in LLM-as-judge scoring with calibration — more signal but circular (see evaluation circularity TODO above); (c) hybrid approach: structural metrics for basic validation + optional LLM scoring for deeper quality assessment. Recommend starting with (a) for v1 and iterating toward (c). Update T7c effort estimate after this investigation concludes.

**Effort:** M (human: ~1 day research / CC: ~30min)
**Priority:** P1
**Depends on:** Evaluation circularity investigation (above).

## Completed

### Phase 0: Bug Fixes (T1, T2, T2-ext, T3)

Replaced self-assessment with external TaskEvaluator protocol, fixed {k} placeholder, added deep-copy + audit rollback.

### Phase 1: Test Suite Infrastructure (T7a, T7b, T7c)

Added EvalCase/ScoreResult models with JSONL serialization, test suite loader, and structural scoring functions for strategy_generation and trajectory_comparison meta-skills. Each suite has 6 test cases including adversarial and edge cases. Scoring uses deterministic metrics (v1) to avoid evaluation circularity.
