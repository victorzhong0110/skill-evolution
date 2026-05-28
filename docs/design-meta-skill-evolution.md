# Design: Meta-Skill Evolution via External Evaluation

**Status:** Draft
**Date:** 2026-05-27
**Author:** victorzhong0110
**Decision:** Approach B — External evaluation-driven evolution with ground-truth test sets, one-at-a-time evolution, regression gates, and auto-snapshot rollback.

## Problem

The four meta-skills (strategy generation, trajectory comparison, skill patching, audit) form a multiplicative bottleneck: if any one degrades, every skill evolved through the pipeline degrades proportionally. Self-evaluation creates a positive feedback loop — a degraded Comparator would rate its own flawed comparisons as correct, reinforcing errors.

### Known Bugs (Must Fix First)

1. **`{k}` placeholder bug** — `explorer.py:83` calls `self._system_prompt.replace("{k}", str(k))`, but `strategy_generation.md` contains no `{k}` placeholder. When loaded from markdown (not fallback), the LLM doesn't know how many strategies to generate.
2. **Self-assessment reliability** — `executor.py` has the executing agent self-report SUCCESS/FAILURE. Both SkillEvolver and EmbodiSkill papers use external ground-truth evaluation instead.

## Design Principles

1. **External evaluation over self-evaluation** — Every meta-skill is evaluated against ground-truth test data, never by itself or another meta-skill.
2. **One-at-a-time evolution** — Evolve a single meta-skill per cycle while holding the other three frozen. Isolates causality.
3. **Regression gate** — A meta-skill update is accepted only if it passes all existing test cases AND improves on at least one. No silent degradation.
4. **Auto-snapshot + rollback** — Before any evolution attempt, snapshot the current meta-skill file. If regression is detected, rollback is automatic.
5. **Reuse existing pipeline** — The same Explorer → Executor → Comparator → Patcher → Auditor pipeline evolves meta-skills, with the external evaluation harness replacing self-assessment.

## Architecture

### Components

```
┌─────────────────────────────────────────────────────┐
│                  Meta-Skill Evolver                  │
│                                                     │
│  ┌───────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ Test Suite │  │  Snapshot  │  │   Regression  │  │
│  │  Loader    │  │  Manager   │  │   Gate        │  │
│  └─────┬─────┘  └─────┬──────┘  └──────┬────────┘  │
│        │               │                │            │
│        ▼               ▼                ▼            │
│  ┌─────────────────────────────────────────────┐    │
│  │         Existing Pipeline (frozen 3/4)       │    │
│  │  Explorer → Executor → Comparator → Patcher  │    │
│  └─────────────────────────────────────────────┘    │
│        │                                             │
│        ▼                                             │
│  ┌──────────────┐                                    │
│  │  External     │  ← Ground-truth test cases        │
│  │  Evaluator    │  → Score + regression check       │
│  └──────────────┘                                    │
└─────────────────────────────────────────────────────┘
```

### Test Suite Structure

Each meta-skill gets a test directory:

```
tests/meta_skill_eval/
├── strategy_generation/
│   ├── cases.jsonl          # Input scenarios + expected properties
│   └── scoring.py           # Evaluation functions
├── trajectory_comparison/
│   ├── cases.jsonl
│   └── scoring.py
├── skill_patch/
│   ├── cases.jsonl
│   └── scoring.py
└── skill_audit/
    ├── cases.jsonl
    └── scoring.py
```

Each `cases.jsonl` line:

```json
{
  "id": "strat-001",
  "input": { "task_description": "...", "skill_text": "...", "k": 4 },
  "expected": {
    "count": 4,
    "diversity_axes": ["decomposition", "reasoning_style"],
    "grounded_in_skill": true
  },
  "tags": ["basic", "diversity"]
}
```

Each `scoring.py` implements:

```python
def evaluate(meta_skill_output: str, expected: dict) -> EvalResult:
    """Returns score (0-1) and per-criterion breakdown."""
    ...
```

Scoring is deterministic and programmatic where possible (count checks, structural validation, keyword presence). For semantic quality, use a frozen LLM call with a fixed evaluation prompt that is NOT one of the four meta-skills.

### Snapshot Manager

```python
class SnapshotManager:
    def snapshot(self, meta_skill_name: str) -> Path:
        """Copy current meta-skill file to snapshots/ with timestamp."""

    def rollback(self, meta_skill_name: str, snapshot_path: Path) -> None:
        """Restore meta-skill from snapshot."""

    def list_snapshots(self, meta_skill_name: str) -> list[SnapshotInfo]:
        """List available snapshots with scores."""
```

Storage: `~/.skill-evolution/snapshots/{meta_skill_name}/{timestamp}.md`

### Regression Gate

```python
class RegressionGate:
    def check(
        self,
        baseline_scores: dict[str, float],
        candidate_scores: dict[str, float],
    ) -> GateResult:
        """
        PASS: no test regresses AND at least one improves.
        FAIL: any test score drops below baseline.
        """
```

### Evolution Cycle

```
For each meta-skill M (one at a time):
  1. Snapshot M
  2. Run test suite on M → baseline_scores
  3. Freeze the other 3 meta-skills
  4. Run pipeline: explore strategies to improve M
  5. Execute strategies, compare trajectories, patch M
  6. Run test suite on candidate M → candidate_scores
  7. Regression gate: compare baseline vs candidate
     - PASS → accept candidate, log improvement
     - FAIL → rollback to snapshot, log failure reason
  8. Auditor reviews final state
```

### CLI Extension

```
skill-evolution meta-evolve [--target NAME] [--rounds N] [--dry-run]
skill-evolution meta-test [--target NAME]
skill-evolution meta-snapshot list [--target NAME]
skill-evolution meta-snapshot rollback --target NAME --snapshot ID
```

## Implementation Phases

### Phase 0: Fix Bugs (prerequisite)

- Add `{k}` placeholder to `strategy_generation.md`
- Replace self-assessment in `executor.py` with external evaluation interface
- Add tests for both fixes

### Phase 1: Test Suite Infrastructure

- Define `EvalResult` and `EvalCase` data models
- Implement test suite loader (`cases.jsonl` → `EvalCase` list)
- Implement scoring functions for each meta-skill
- Build 5-10 test cases per meta-skill from real or synthetic examples
- CLI: `skill-evolution meta-test`

### Phase 2: Snapshot + Regression Gate

- Implement `SnapshotManager`
- Implement `RegressionGate`
- CLI: `skill-evolution meta-snapshot`

### Phase 3: Evolution Cycle

- Implement `MetaSkillEvolver` orchestrator
- Wire up: snapshot → baseline → evolve → candidate → gate → accept/rollback
- CLI: `skill-evolution meta-evolve`

### Phase 4: Validation

- Run meta-evolve on each meta-skill with synthetic tasks
- Verify regression gate catches intentional degradation
- Verify rollback works correctly
- Document results

## Test Case Design Guidelines

### Strategy Generation

- **Diversity**: Given a task, do generated strategies cover distinct axes?
- **Count**: Does it generate exactly K strategies?
- **Grounding**: Are strategies grounded in the skill text, not generic?
- **Actionability**: Can each strategy be executed without clarification?

### Trajectory Comparison

- **Contrastive focus**: Does it identify winner-specific behaviors?
- **Root cause depth**: Does it go beyond surface observations?
- **Signal quality**: Are delta signals categorized correctly (missing_knowledge, wrong_approach, etc.)?
- **Confidence calibration**: High-confidence signals should have strong evidence.

### Skill Patching

- **Precision**: Does the patch change only what the signal targets?
- **Preservation**: Is existing correct content preserved?
- **Body/appendix routing**: Are changes applied to the correct section?
- **Changelog accuracy**: Does the changelog describe what actually changed?

### Skill Audit

- **Detection**: Does it catch planted overfitting/hardcoding/bypass issues?
- **False positive rate**: Does it avoid flagging correct patterns?
- **Severity calibration**: FAIL/WARNING/PASS thresholds are correct.
- **Independence**: Audit result should not be influenced by the skill author.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Test suite itself is low quality | Start with deterministic structural checks; add semantic evaluation gradually |
| LLM-based scoring is nondeterministic | Use temperature=0, fixed seed where supported; run each eval 3x and take majority |
| Evolution makes no progress | Log detailed failure reasons; consider loosening diversity in strategy generation |
| Ground-truth becomes stale | Review test suite quarterly; add new cases from real evolution runs |

## Non-Goals

- **Cross-evaluation architecture** (Approach C) — deferred. Can layer on top of B later if meta-skill quality reaches a sufficient baseline.
- **Automated test case generation** — manual curation for v1; automation is a future enhancement.
- **Multi-meta-skill simultaneous evolution** — explicitly avoided; one-at-a-time is a safety invariant.

## References

- SkillEvolver (arXiv:2605.10500): Independent fresh-agent audit, contrastive skill updates
- EmbodiSkill (arXiv:2605.10332): Body/Appendix structure, targeted revision over whole-skill rewrite
