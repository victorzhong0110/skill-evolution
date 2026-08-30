# skill-evolution

[![CI](https://github.com/victorzhong0110/skill-evolution/actions/workflows/ci.yml/badge.svg)](https://github.com/victorzhong0110/skill-evolution/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/skill-evolution)](https://pypi.org/project/skill-evolution/)
[![Python](https://img.shields.io/pypi/pyversions/skill-evolution)](https://pypi.org/project/skill-evolution/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> Evolve Agent Skills (`SKILL.md`) through a contrastive loop with a held-out gate.

Portable CLI for improving **your** skill tonight — not a SkillOpt-scale trainer.
Inspired by [SkillEvolver](https://arxiv.org/abs/2605.10500) and
[EmbodiSkill](https://arxiv.org/abs/2605.10332). The 0.2 loop also takes the
validation gate from [SkillOpt](https://arxiv.org/abs/2605.23904), first-class
DELETE/DEMOTE from [SkillProx](https://arxiv.org/abs/2608.07449), and the
[Agent Skills](https://agentskills.io/specification) directory format.

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
    │  2. Task Executor        │  Run each strategy; optional scripts/
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  3. External Evaluator   │  Task keywords / patterns (no self-grade)
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  4. Trajectory Comparator│  Success vs failure → delta signals
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  5. Skill Patcher        │  ADD / REFINE / DEMOTE / DELETE
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────┐
    │  6. Auditor + held-out   │  SkillJack provenance, shrinkage, gate
    └────────────┬────────────┘
                 │
          ┌──────▼───────┐
          │ Evolved Skill │──── repeat for R rounds
          └──────────────┘
```

Key design principles:

- **Contrastive updates**: signals come from successful vs failed trajectories
- **Scorable tasks**: an empty `KeywordEvaluator` is refused (it would mark every run SUCCESS)
- **Held-out gate**: train patches that drop held-out scores are rolled back (SkillOpt)
- **Shrinkage**: DELETE/DEMOTE are first-class; growth-only patches are a defect (SkillProx)
- **Independent audit**: overfitting, silent bypass, provenance / SkillJack

## Quick Start

### Install

```bash
pip install skill-evolution
```

Or for development:

```bash
git clone https://github.com/victorzhong0110/skill-evolution.git
cd skill-evolution && pip install -e ".[dev]"
```

### Evolve a public-format skill (recommended)

Flagship example is adapted from [alibaba/skill-up](https://github.com/alibaba/skill-up)
`code-stats` (Apache-2.0): a real Agent Skills directory with `SKILL.md`,
`scripts/`, and train / held-out tasks.

```bash
# Claude Code CLI auth — no API key
skill-evolution evolve examples/code-stats examples/code-stats/tasks.json \
  --provider cli --rounds 1 --strategies 2

# Or Anthropic API
export ANTHROPIC_API_KEY=sk-...
skill-evolution evolve examples/code-stats examples/code-stats/tasks.json \
  --provider claude --model claude-sonnet-4-6 --rounds 1 --strategies 2
```

Second example, original spec-shaped design skill (not a copy of Anthropic's
proprietary `frontend-design` body):

```bash
skill-evolution evolve examples/frontend-design examples/frontend-design/tasks.json \
  --provider cli --rounds 1 --strategies 2
```

### Audit a skill

```bash
skill-evolution audit examples/code-stats
```

### View version history

```bash
skill-evolution history code-stats --workspace .skill-evolution
```

### Rollback

```bash
skill-evolution rollback code-stats 2 --workspace .skill-evolution
```

### Generate default config

```bash
skill-evolution init
```

## Skill Format

Skills are an [Agent Skills](https://agentskills.io/specification) directory
or a single Markdown file. Directories are preferred:

```
my-skill/
├── SKILL.md          # required: YAML name + description, then instructions
├── scripts/          # optional; executor may run these under scripts/
├── references/       # optional; loaded on demand
└── assets/
```

```markdown
---
name: my-skill
description: What it does and when to trigger it. Both belong here.
license: MIT
---

# Skill Body

Core rules and knowledge go here.

## Appendix

Reinforcement reminders for rules agents tend to skip.
```

`name` should be lowercase digits and single hyphens. `description` is required
by the spec and is the trigger text hosts show to the model.

Passing a directory (or `SKILL.md`) writes `name.evolved/` beside it. Passing a
`.md` file writes `*.evolved.md`.

## Task Format

Plain text still works for prompts, but **evolution needs scoring criteria**.
Use JSON with `required` / `forbidden` / `expected_patterns`, and a held-out
split so the gate can reject overfit patches:

```json
{
  "train": [
    {"id": "t1", "prompt": "Analyze ./src", "required": ["Files by Extension", "Total Files"]}
  ],
  "held_out": [
    {"id": "h1", "prompt": "Analyze ./tests", "required": ["Largest Files", "Total Lines"]}
  ]
}
```

Also accepted:

- JSON array of strings (all train; still needs a configured evaluator)
- skill-creator `{ "evals": [ { "prompt", "expectations": [...] } ] }` — last third held-out
- YAML with the same shapes

Without criteria on tasks **and** without a configured evaluator, `evolve`
exits with code 2.

## Configuration

Generate a config file with `skill-evolution init`, then edit `skill-evolution.yaml`:

```yaml
llm:
  provider: claude          # claude | openai | cli | bridge
  model: claude-sonnet-4-6
  temperature: 0.7
evolution:
  num_strategies: 4         # K: strategies per task per round
  num_rounds: 2             # R: evolution rounds
  budget_usd: 10.0          # Max spend (null = unlimited)
  held_out_gate: true       # Roll back patches that drop held-out scores
  gate_tolerance: 0.0
  auto_snapshot: true
audit:
  enabled: true
  checks:
    - overfitting
    - hardcoding
    - silent_bypass
    - consistency
    - generalizability
    - provenance
    - shrinkage
workspace_dir: .skill-evolution
```

## Architecture

```
src/skill_evolution/
├── cli.py              # CLI commands (evolve, audit, history, rollback, init)
├── config.py           # YAML configuration
├── llm/                # LLM abstraction (Claude + OpenAI compatible)
├── skill/              # Skill schema + version management + regression gate
├── evaluation/         # Task specs, KeywordEvaluator, PerTaskEvaluator
├── core/               # Evolution engine
│   ├── explorer.py     # Strategy diversification
│   ├── comparator.py   # Contrastive trajectory analysis
│   ├── patcher.py      # ADD / REFINE / DEMOTE / DELETE
│   ├── auditor.py      # Independent quality audit
│   └── pipeline.py     # Orchestrates the full loop
├── runner/             # Task execution + scripts/ sandbox
│   └── executor.py
└── meta_skills/        # Built-in meta-skills (themselves evolvable)
    ├── strategy_generation.md
    ├── trajectory_comparison.md
    ├── skill_audit.md
    └── skill_patch.md
```

## Meta-Skills: The Bootstrap

The four meta-skills in `meta_skills/` drive the evolution process itself. They can be evolved using the same pipeline — making the system self-improving:

```bash
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
  author={Ju, Ruofei and Wang, Xinrui and Ding, Xin and Yang, Yifan and Wu, Hao
          and Jiang, Shiqi and Zhang, Qianxi and Wen, Hao and Li, Xiangyu
          and Wang, Weijun and Li, Kun and Liu, Yunxin and Dai, Haipeng
          and Wang, Wei and Cao, Ting},
  journal={arXiv preprint arXiv:2605.10332},
  year={2026}
}

@article{skillopt2026,
  title={SkillOpt: Executive Strategy for Self-Evolving Agent Skills},
  author={Yang, Yifan and Gong, Ziyang and Huang, Weiquan and Yang, Qihao and Zhou, Ziwei
          and Huang, Zisu and Li, Yan and Gao, Xuemei and Dai, Qi and Liu, Bei
          and Qiu, Kai and Yang, Yuqing and Chen, Dongdong and Yang, Xue and Luo, Chong},
  journal={arXiv preprint arXiv:2605.23904},
  year={2026}
}

@article{skillprox2026,
  title={SkillProx: Self-Evolving Agent Skills via Proximal Textual Gradient Descent},
  author={Zheng, Mingxuan and Zhou, Yujin and Cao, Chuxue and Yin, Boqin and Zhang, Yuyao
          and Sun, Jiapeng and Gong, Shuaishuai and Han, Sirui and Guo, Yike},
  journal={arXiv preprint arXiv:2608.07449},
  year={2026}
}

@article{skilljack2026,
  title={SkillJack: Persistent Skill Backdoors in Self-Evolving Agents},
  author={Ying, Zonghao and Wu, Xiangfan and Wu, Huiyu and Zheng, Xing
          and Cheng, Huangsheng and Shi, Xiaorong and Guo, Jing},
  journal={arXiv preprint arXiv:2608.03509},
  year={2026}
}
```

EmbodiSkill authors: Ruofei Ju, Xinrui Wang, Xin Ding, Yifan Yang, Hao Wu,
Shiqi Jiang, Qianxi Zhang, Hao Wen, Xiangyu Li, Weijun Wang, Kun Li, Yunxin Liu,
Haipeng Dai, Wei Wang, Ting Cao ([arXiv 2605.10332](https://arxiv.org/abs/2605.10332)).

Examples cite [agentskills.io](https://agentskills.io/specification),
[anthropics/skills](https://github.com/anthropics/skills) (directory format only),
and [alibaba/skill-up](https://github.com/alibaba/skill-up) `code-stats`.

## License

MIT
