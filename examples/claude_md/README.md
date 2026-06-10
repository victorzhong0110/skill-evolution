# Example: evolve your CLAUDE.md

Every Claude Code user has a `CLAUDE.md` — guidance the assistant reads before
acting. Most of them are written once and never improved. This example evolves
one the same way you would evolve any skill document: run realistic tasks
against it, compare what worked, patch the guidance, audit the patch.

`skill.md` here is a deliberately thin starting point ("write clean code, add
tests") so the evolution loop has visible headroom.

## Run it

No API key needed if you have the `claude` CLI installed (uses your existing
Claude Code authentication):

```bash
skill-evolution evolve examples/claude_md/skill.md examples/claude_md/tasks.txt \
  --provider cli --rounds 1 --strategies 2
```

With an API key instead:

```bash
export ANTHROPIC_API_KEY=sk-...
skill-evolution evolve examples/claude_md/skill.md examples/claude_md/tasks.txt \
  --provider claude --rounds 1 --strategies 2
```

The evolved skill is written next to the original (or use `--output`), and every
round is snapshotted — inspect with:

```bash
skill-evolution history claude-md
```

## Adapting it to your real CLAUDE.md

1. Copy your project's `CLAUDE.md` body into a skill file with front matter
   (see [Skill Format](../../README.md#skill-format)).
2. Write 3-10 tasks that look like the requests you actually give the
   assistant — evolution quality tracks task realism.
3. Run a round, read the diff, keep what you like. The auditor rolls back
   regressions automatically, but you stay the editor-in-chief.
