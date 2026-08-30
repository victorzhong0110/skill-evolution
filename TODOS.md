# TODOS

## Open (0.3)

- Fuller agent backends (tool-using executors beyond `===RUN_SCRIPT===`).
- SkillCommit-style instance patch then behavioral abstraction.
- Publish a measured before/after (cost, success rate, audit rollbacks) before promoting.

## Completed

### 0.2.0

Empty KeywordEvaluator hard-fail. Held-out gate. Agent Skills directories.
DELETE/DEMOTE + SkillJack provenance audit. Examples from skill-up / spec, not CLAUDE.md.

### Phase 0: Bug Fixes (T1, T2, T2-ext, T3)

Replaced self-assessment with external TaskEvaluator protocol, fixed {k} placeholder, added deep-copy + audit rollback.

### Phase 1: Test Suite Infrastructure (T7a, T7b, T7c)

Added EvalCase/ScoreResult models with JSONL serialization, test suite loader, and structural scoring functions for strategy_generation and trajectory_comparison meta-skills.

### Phase 2: Snapshot + Regression Gate (T8)

Extended SkillVersionManager with per-version score maps. Added RegressionGate (check_regression).

### Phase 3: Evolution Cycle (T9)

MetaSkillEvolver orchestrator with full cycle and CLI commands: meta-evolve, meta-test, meta-snapshot.

### Cleanup Batch (T4, T5, T10, T12, T13)

DRY prompt deduplication, logger.warning for malformed YAML, doctor CLI command, structured changelog, score trend display.

### Integration Tests + Rich Output (T6, T11)

Pipeline integration tests with MockLLM. Rich score comparison table in MetaSkillEvolver.
