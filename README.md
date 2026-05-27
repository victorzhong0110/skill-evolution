# skill-evolution

> Evolve AI agent skills through iterative meta-skill-driven optimization.

Inspired by [SkillEvolver](https://arxiv.org/abs/2605.10500) and [EmbodiSkill](https://arxiv.org/abs/2605.10332), `skill-evolution` is a framework-agnostic CLI tool that automatically improves AI agent skill documents through a principled evolution loop.

## How It Works

```
          ┌─────────────┐
          │ Initial Skill│
          └──────┬───────┘
                 │
    ┌────────────▼────────────┐
    │  1. Strategy Explorer    │  Generate K diverse approaches
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  2. Task Executor        │  Run each strategy independently
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  3. Trajectory Comparator│  Compare success vs failure → delta signals
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  4. Skill Patcher        │  Apply targeted patches (not rewrites)
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  5. Independent Auditor  │  Check for overfitting, hardcoding, etc.
    └────────────┬────────────┘
                 │
          ┌──────▼───────┐
          │ Evolved Skill │──── repeat for R rounds
          └──────────────┘
```

Key design principles:
- **Contrastive updates**: improvement signals come from comparing successful vs failed trajectories, not from self-reflection
- **Targeted patching**: only modify what signals indicate — preserve everything else
- **Skill-aware attribution**: distinguish skill defects (fix the body) from execution lapses (reinforce in appendix)
- **Independent audit**: a separate LLM instance reviews evolved skills for overfitting

## Quick Start

### Install

```bash
pip install -e .
```

### Evolve a skill

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-...
# or for OpenAI:
# export OPENAI_API_KEY=sk-...

# Run evolution (2 rounds, 4 strategies per task)
skill-evolution evolve examples/code_review/skill.md examples/code_review/tasks.txt

# With options
skill-evolution evolve examples/code_review/skill.md examples/code_review/tasks.txt \
  --rounds 3 \
  --strategies 4 \
  --budget 5.0 \
  --provider claude \
  --model claude-sonnet-4-20250514
```

### Audit a skill

```bash
skill-evolution audit my-skill.md
```

### View version history

```bash
skill-evolution history code-review --workspace .skill-evolution
```

### Rollback

```bash
skill-evolution rollback code-review 2 --workspace .skill-evolution
```

### Generate default config

```bash
skill-evolution init
```

## Skill Format

Skills are Markdown files with YAML front matter:

```markdown
---
name: my-skill
version: 0
domain: engineering
tags: [example]
---

# Skill Body

Core rules and knowledge go here.

## Appendix

Reinforcement reminders for rules agents tend to skip.
```

## Task Format

Tasks are plain text files, one task per line:

```
Review this code for SQL injection vulnerabilities: `query = f"SELECT * FROM users WHERE id = {user_id}"`
Analyze this function for performance issues: `def find(items): return [x for x in items if x in other_list]`
```

Or JSON arrays:

```json
["Task 1 description", "Task 2 description"]
```

## Configuration

Generate a config file with `skill-evolution init`, then edit `skill-evolution.yaml`:

```yaml
llm:
  provider: claude          # claude | openai
  model: claude-sonnet-4-20250514
  temperature: 0.7
evolution:
  num_strategies: 4         # K: strategies per task per round
  num_rounds: 2             # R: evolution rounds
  budget_usd: 10.0          # Max spend (null = unlimited)
  auto_snapshot: true
audit:
  enabled: true
workspace_dir: .skill-evolution
```

## Architecture

```
src/skill_evolution/
├── cli.py              # CLI commands (evolve, audit, history, rollback, init)
├── config.py           # YAML configuration
├── llm/                # LLM abstraction (Claude + OpenAI compatible)
├── skill/              # Skill schema + version management
├── core/               # Evolution engine
│   ├── explorer.py     # Strategy diversification
│   ├── comparator.py   # Contrastive trajectory analysis
│   ├── patcher.py      # Targeted skill patching
│   ├── auditor.py      # Independent quality audit
│   └── pipeline.py     # Orchestrates the full loop
├── runner/             # Task execution
│   └── executor.py     # Independent agent execution
└── meta_skills/        # Built-in meta-skills (themselves evolvable)
    ├── strategy_generation.md
    ├── trajectory_comparison.md
    ├── skill_audit.md
    └── skill_patch.md
```

## Meta-Skills: The Bootstrap

The four meta-skills in `meta_skills/` drive the evolution process itself. They can be evolved using the same pipeline — making the system self-improving:

```bash
# Evolve the strategy generation meta-skill using its own pipeline
skill-evolution evolve src/skill_evolution/meta_skills/strategy_generation.md meta_skill_tasks.txt
```

## Citation

If you use this tool in research, please cite the papers that inspired it:

```bibtex
@article{skillevolver2026,
  title={SkillEvolver: Skill Learning as a Meta-Skill},
  author={Zhang, Genrui and Zhu, Erle and Zhou, Jinfeng and Jia, Caiyan and Wang, Hongning},
  journal={arXiv preprint arXiv:2605.10500},
  year={2026}
}

@article{embodiskill2026,
  title={EmbodiSkill: Skill-Aware Reflection for Self-Evolving Embodied Agents},
  author={...},
  journal={arXiv preprint arXiv:2605.10332},
  year={2026}
}
```

## License

MIT
