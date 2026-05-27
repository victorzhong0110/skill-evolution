"""Tests for the trajectory comparator — signal parsing."""

from __future__ import annotations

import pytest

from skill_evolution.core.comparator import Comparator, DeltaSignal


class TestSignalParsing:
    def test_parse_well_formed_signals(self):
        text = """\
===SIGNAL 1===
Category: missing_knowledge
Affects: body
Confidence: 0.85
Description: Skill lacks SQL injection detection patterns
Evidence: Failed trajectory missed parameterized query check

===SIGNAL 2===
Category: edge_case
Affects: appendix
Confidence: 0.6
Description: Skill doesn't cover NoSQL injection
Evidence: MongoDB query was not flagged

===END===
"""
        comparator = Comparator.__new__(Comparator)
        signals = comparator._parse_signals(text)

        assert len(signals) == 2
        assert signals[0].category == "missing_knowledge"
        assert signals[0].affects == "body"
        assert signals[0].confidence == 0.85
        assert "SQL injection" in signals[0].description
        assert signals[1].affects == "appendix"

    def test_parse_no_signals(self):
        comparator = Comparator.__new__(Comparator)
        signals = comparator._parse_signals("===NO_SIGNALS===")
        assert signals == []

    def test_parse_clamps_confidence(self):
        text = """\
===SIGNAL 1===
Category: wrong_approach
Affects: body
Confidence: 1.5
Description: Over-confident signal
Evidence: test
===END===
"""
        comparator = Comparator.__new__(Comparator)
        signals = comparator._parse_signals(text)
        assert signals[0].confidence == 1.0

    def test_parse_invalid_confidence_defaults(self):
        text = """\
===SIGNAL 1===
Category: missing_knowledge
Affects: body
Confidence: not_a_number
Description: Bad confidence value
Evidence: test
===END===
"""
        comparator = Comparator.__new__(Comparator)
        signals = comparator._parse_signals(text)
        assert signals[0].confidence == 0.5

    def test_parse_invalid_affects_defaults_to_body(self):
        text = """\
===SIGNAL 1===
Category: efficiency
Affects: invalid_target
Confidence: 0.7
Description: Bad target
Evidence: test
===END===
"""
        comparator = Comparator.__new__(Comparator)
        signals = comparator._parse_signals(text)
        assert signals[0].affects == "body"

    def test_parse_skips_signals_without_description(self):
        text = """\
===SIGNAL 1===
Category: missing_knowledge
Affects: body
Confidence: 0.5
Evidence: only evidence no description
===END===
"""
        comparator = Comparator.__new__(Comparator)
        signals = comparator._parse_signals(text)
        assert signals == []
