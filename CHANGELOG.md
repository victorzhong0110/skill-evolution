# Changelog

## Unreleased

### Added

- Bounded HTTP retries + configurable timeout for Claude and OpenAI-compatible
  clients (`timeout_s=60`, `max_retries=3`, `retry_backoff_s=0.5`; cap 6 retries).
  Transient only: timeout, 429, 5xx. SDK retries disabled to avoid nested loops.
- `requirements-dev.txt` lock; CI installs from it. Python matrix 3.11–3.13.
- GitHub Actions pinned to full commit SHAs (not floating `@v4` / `@v5`).

### Changed

- Executor / docs: `scripts/` runner is a **path-jail host subprocess**
  (relative `scripts/` path, inherits `os.environ`, ~30s timeout). Not Docker
  and not container isolation.

## 0.2.0 — 2026-08-30

Agent Skills packages, a scorable evaluator, and a held-out promotion gate.

### Breaking

- `evolve` refuses an empty `KeywordEvaluator` unless every task carries scoring
  criteria (`required` / `forbidden` / `expected_patterns`). Exit code 2 on the CLI.
- Default LLM model is `claude-sonnet-4-6` (was documented as `claude-sonnet-4-20250514`).
- Directory / `SKILL.md` inputs write `name.evolved/` instead of a sibling `.md` file.

### Added

- Agent Skills directory load/save: `name` + `description`, `scripts/`, `references/`.
- Task files with `{train, held_out}` and skill-creator `{evals: [...]}`.
- SkillOpt-style held-out regression gate (`evolution.held_out_gate`).
- Patch operations DELETE / DEMOTE; shrinkage signal when a patch grows >25% with no DELETE.
- Script path-jail under `package_dir/scripts/` (`===RUN_SCRIPT===`); silent-bypass via `===SKILL_USED===`.
- Auditor checks: provenance (SkillJack), shrinkage; runtime silent-bypass when trajectories never invoke the skill.
- Flagship examples from public GitHub skills:
  - `examples/code-stats/` adapted from alibaba/skill-up (Apache-2.0)
  - `examples/frontend-design/` original spec-shaped skill (not a copy of Anthropic's proprietary body)

### Changed

- PyPI author is `victorzhong0110`. EmbodiSkill citation lists the paper authors.
- `claude_md` is a secondary example; start with `code-stats`.

## 0.1.0

Initial public CLI: SkillEvolver / EmbodiSkill loop, meta-skill evolution, Claude/OpenAI/cli/bridge backends.
