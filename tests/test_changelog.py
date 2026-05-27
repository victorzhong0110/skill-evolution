"""Tests for evolution changelog (T12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_evolution.core.changelog import (
    ChangelogEntry,
    append_changelog,
    read_changelog,
    read_changelog_for_skill,
)


class TestChangelogEntry:
    def test_defaults(self):
        entry = ChangelogEntry(meta_skill="test", action="accepted")
        assert entry.timestamp
        assert entry.baseline_mean == 0.0
        assert entry.improved == []

    def test_full_entry(self):
        entry = ChangelogEntry(
            meta_skill="strategy_generation",
            action="accepted",
            baseline_mean=0.6,
            candidate_mean=0.8,
            delta=0.2,
            improved=["sg-001", "sg-002"],
            version=3,
            summary="PASS: 2 improved",
        )
        assert entry.delta == 0.2
        assert len(entry.improved) == 2


class TestAppendAndRead:
    def test_append_creates_file(self, tmp_path: Path):
        entry = ChangelogEntry(meta_skill="test", action="accepted")
        path = append_changelog(tmp_path, entry)
        assert path.exists()

    def test_roundtrip(self, tmp_path: Path):
        entries = [
            ChangelogEntry(meta_skill="a", action="accepted", delta=0.1),
            ChangelogEntry(meta_skill="b", action="rejected", delta=-0.05),
            ChangelogEntry(meta_skill="a", action="accepted", delta=0.2),
        ]
        for e in entries:
            append_changelog(tmp_path, e)

        loaded = read_changelog(tmp_path)
        assert len(loaded) == 3
        assert loaded[0].meta_skill == "a"
        assert loaded[1].action == "rejected"

    def test_read_empty(self, tmp_path: Path):
        assert read_changelog(tmp_path) == []

    def test_filter_by_skill(self, tmp_path: Path):
        append_changelog(tmp_path, ChangelogEntry(meta_skill="a", action="accepted"))
        append_changelog(tmp_path, ChangelogEntry(meta_skill="b", action="rejected"))
        append_changelog(tmp_path, ChangelogEntry(meta_skill="a", action="accepted"))

        filtered = read_changelog_for_skill(tmp_path, "a")
        assert len(filtered) == 2
        assert all(e.meta_skill == "a" for e in filtered)
