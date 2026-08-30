# Example: evolve a CLAUDE.md

Secondary example. For a public Agent Skills package with scripts and a
held-out split, start with [examples/code-stats/](../code-stats/) instead.

`skill.md` here is a thin starting point so the loop has visible headroom.

```bash
skill-evolution evolve examples/claude_md/skill.md examples/claude_md/tasks.txt \
  --provider cli --rounds 1 --strategies 2
```

Plain `tasks.txt` has no scoring criteria. Evolution will refuse unless you
add `required` keywords in a JSON task file, or pass a configured evaluator.
Prefer copying the `tasks.json` shape from `examples/code-stats/`.
