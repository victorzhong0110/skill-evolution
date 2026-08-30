"""Task specifications with train / held-out splits.

Adopted from skill-up (evals.json) and SkillOpt (held-out selection split):
each task can carry its own scoring criteria so evolution is never judged by
an empty KeywordEvaluator that marks every trajectory SUCCESS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Split = Literal["train", "held_out"]


@dataclass
class TaskSpec:
    """One evaluable task used during skill evolution."""

    prompt: str
    id: str = ""
    split: Split = "train"
    required: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    expected_patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            slug = self.prompt.strip().split("\n")[0][:40]
            self.id = slug or "task"

    @property
    def has_criteria(self) -> bool:
        return bool(self.required or self.forbidden or self.expected_patterns)


def normalize_tasks(tasks: list[str] | list[TaskSpec]) -> list[TaskSpec]:
    """Accept plain strings (legacy) or TaskSpec objects."""
    out: list[TaskSpec] = []
    for i, item in enumerate(tasks):
        if isinstance(item, TaskSpec):
            if not item.id:
                item.id = f"task-{i+1}"
            out.append(item)
        else:
            out.append(TaskSpec(id=f"task-{i+1}", prompt=str(item)))
    return out


def load_task_specs(path: str | Path) -> list[TaskSpec]:
    """Load tasks from txt, JSON, JSONL, YAML, or a skill-up / skill-creator evals file."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if file_path.suffix in {".yaml", ".yml"}:
        return _from_obj(yaml.safe_load(text) or {}, default_id_prefix=file_path.stem)

    if text.startswith("{") or text.startswith("["):
        return _from_obj(json.loads(text), default_id_prefix=file_path.stem)

    specs: list[TaskSpec] = []
    for i, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("{") and stripped.endswith("}"):
            specs.extend(_from_obj(json.loads(stripped), default_id_prefix=f"line-{i}"))
            continue
        specs.append(TaskSpec(id=f"task-{len(specs)+1}", prompt=stripped))
    return specs


def _from_obj(data: Any, default_id_prefix: str = "task") -> list[TaskSpec]:
    if isinstance(data, list):
        specs: list[TaskSpec] = []
        for i, item in enumerate(data, start=1):
            specs.append(_one(item, default_id=f"{default_id_prefix}-{i}", split="train"))
        return specs

    if not isinstance(data, dict):
        raise ValueError(f"Unsupported task file payload: {type(data).__name__}")

    if "evals" in data and isinstance(data["evals"], list):
        specs = []
        for i, item in enumerate(data["evals"], start=1):
            specs.append(_one(item, default_id=str(item.get("id", i)), split="train"))
        n_held = max(1, len(specs) // 3) if len(specs) >= 3 else 0
        if n_held:
            for spec in specs[-n_held:]:
                spec.split = "held_out"
        return specs

    specs = []
    for split in ("train", "held_out"):
        items = data.get(split) or []
        if isinstance(items, str):
            items = [items]
        for i, item in enumerate(items, start=1):
            specs.append(_one(item, default_id=f"{split}-{i}", split=split))  # type: ignore[arg-type]
    if specs:
        return specs

    if "prompt" in data or "task" in data:
        return [_one(data, default_id=default_id_prefix, split="train")]

    raise ValueError(
        "Task file must be a JSON array, {train, held_out} object, or skill-creator {evals: [...]}."
    )


def _one(item: Any, *, default_id: str, split: Split) -> TaskSpec:
    if isinstance(item, str):
        return TaskSpec(id=default_id, prompt=item, split=split)
    if not isinstance(item, dict):
        raise ValueError(f"Task entry must be a string or object, got {type(item).__name__}")

    prompt = str(item.get("prompt") or item.get("task") or item.get("description") or "")
    if not prompt:
        raise ValueError(f"Task {default_id!r} is missing prompt/task/description")

    required = _str_list(item.get("required"))
    forbidden = _str_list(item.get("forbidden"))
    patterns = _str_list(item.get("expected_patterns") or item.get("patterns"))
    if not required:
        required = _keywords_from_expectations(item.get("expectations") or [])

    item_split = item.get("split", split)
    if item_split not in ("train", "held_out"):
        item_split = split

    return TaskSpec(
        id=str(item.get("id", default_id)),
        prompt=prompt,
        split=item_split,  # type: ignore[arg-type]
        required=required,
        forbidden=forbidden,
        expected_patterns=patterns,
    )


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _keywords_from_expectations(expectations: list[Any]) -> list[str]:
    """Turn skill-up style expectation sentences into required keyword phrases."""
    keys: list[str] = []
    blob = " ".join(str(item) for item in expectations)
    for phrase in (
        "Files by Extension",
        "Total Files",
        "Total Lines",
        "Largest Files",
        "Top 5 File Extensions",
    ):
        if phrase in blob and phrase not in keys:
            keys.append(phrase)
    if "|" in blob and "|" not in keys:
        keys.append("|")
    return keys
