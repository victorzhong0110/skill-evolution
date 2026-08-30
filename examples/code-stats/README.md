# code-stats

Flagship example: an [Agent Skills](https://agentskills.io/specification) directory
with `SKILL.md`, bundled `scripts/`, and a train / held-out task split.

Adapted from [alibaba/skill-up](https://github.com/alibaba/skill-up)
`examples/code-stats/` (Apache-2.0). See `SOURCE.md` and `NOTICE`.

This is the format the public ecosystem actually uses — not a CLAUDE.md walkthrough.

## Run it

```bash
skill-evolution evolve examples/code-stats examples/code-stats/tasks.json \
  --provider cli --rounds 1 --strategies 2
```

With an API key:

```bash
export ANTHROPIC_API_KEY=sk-...
skill-evolution evolve examples/code-stats examples/code-stats/tasks.json \
  --provider claude --model claude-sonnet-4-6 --rounds 1 --strategies 2
```

`tasks.json` has two train prompts and one held-out prompt. Each lists `required`
keywords (`Files by Extension`, `Total Files`, …). Evolution will refuse to start
if you pass a plain `tasks.txt` with no criteria and no configured evaluator.

The evolved package is written next to the original as `code-stats.evolved/`
(or `--output`).

skill-creator-shaped `evals.json` also loads: the last third of evals become held-out.
