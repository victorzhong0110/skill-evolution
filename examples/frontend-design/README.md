# frontend-design

Spec-shaped design skill used as a second flagship example.

This is **original** instruction text written for skill-evolution. It follows
the [Agent Skills specification](https://agentskills.io/specification)
(`name` + `description` front matter, directory with `SKILL.md`) and the
public "design skill" category that shows up in high-star lists such as
[anthropics/skills](https://github.com/anthropics/skills) and
[bergside/awesome-design-skills](https://github.com/bergside/awesome-design-skills).

It is **not** a copy of Anthropic's `frontend-design` SKILL.md (that file is
under a proprietary license). Do not paste vendor skill bodies into this repo.

## Run it

```bash
skill-evolution evolve examples/frontend-design examples/frontend-design/tasks.json \
  --provider cli --rounds 1 --strategies 2
```

Train tasks ask for a token sheet (palette + hex, type, signature). The held-out
prompt is a different subject so the auditor / SkillOpt-style gate can catch
overfitting to climbing gyms or record shops.
