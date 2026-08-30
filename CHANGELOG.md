# Changelog

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
- Script sandbox under `package_dir/scripts/` (`===RUN_SCRIPT===`); silent-bypass via `===SKILL_USED===`.
- Auditor checks: provenance (SkillJack), shrinkage; runtime silent-bypass when trajectories never invoke the skill.
- Flagship examples from public GitHub skills:
  - `examples/code-stats/` adapted from alibaba/skill-up (Apache-2.0)
  - `examples/frontend-design/` original spec-shaped skill (not a copy of Anthropic's proprietary body)

### Changed

- PyPI author is `victorzhong0110`. EmbodiSkill citation lists the paper authors.
- `claude_md` is a secondary example; start with `code-stats`.

## 0.1.0

Initial public CLI: SkillEvolver / EmbodiSkill loop, meta-skill evolution, Claude/OpenAI/cli/bridge backends.
