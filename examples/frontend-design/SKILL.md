---
name: frontend-design
description: Produce a distinctive, subject-grounded UI plan and implementation notes. Use when the user asks for a new page, landing, dashboard, or restyle — including requests that never say "design system" but clearly need visual direction.
license: MIT
version: 1
domain: design
tags: [frontend, agent-skills, example]
---

# Frontend Design

Write a short design plan before any markup. The plan is the deliverable the
evolution tasks score; the code comes after the plan is unique to this brief.

## 1. Pin the subject

Name the product or page, who it is for, and the single job of the screen.
If the brief is vague, choose a concrete subject and state the choice. Pull
visual vocabulary from that subject's materials, tools, and vernacular — not
from a generic "SaaS landing" template.

## 2. Token sheet (required)

Publish a compact token sheet in the plan:

- **Palette** — 4–6 named colors with hex values
- **Type** — a display face, a body face, and when needed a utility face for data
- **Layout** — one sentence plus a small ASCII wireframe
- **Signature** — the one element this page should be remembered by

Derive every later CSS choice from this sheet. Do not invent extra colors in code.

## 3. Refuse the three defaults

Unless the brief explicitly asks for one of them, do not ship:

1. Warm cream background + terracotta accent + stock serif display
2. Near-black canvas + a single acid-green or vermilion accent
3. Broadsheet columns with hairline rules and zero radius used as decoration

If your first plan matches any of these, revise the palette or signature and
say what you changed.

## 4. Copy is a design material

Interface words name what a person controls, not how the system is built.
Buttons say the action (`Save changes`, not `Submit`). Errors explain the
failure and the next step. Empty states invite an action.

## 5. Build after the plan

Implement from the token sheet. Keep selector specificity boring. Respect
reduced-motion. Spend boldness on the signature; keep the rest quiet.
