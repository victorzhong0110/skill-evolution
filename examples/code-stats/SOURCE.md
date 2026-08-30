# Provenance

This example is adapted from [alibaba/skill-up](https://github.com/alibaba/skill-up)
`examples/code-stats/` (Apache License 2.0, Copyright 2026 Alibaba Group).

Changes in this tree:
- Bundled `scripts/count_stats.py` so evolution can execute a real script instead of
  asking the model to fake `find` / `wc`.
- Added `tasks.json` with an explicit train / held-out split (SkillOpt-style gate).
- Kept `evals.json` in skill-creator shape so the same prompts load either way.

See `NOTICE` for the required Apache-2.0 attribution.
