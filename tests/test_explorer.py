"""Tests for the strategy explorer — parsing and generation."""

from __future__ import annotations

import pytest

from skill_evolution.core.explorer import Explorer, Strategy


class TestStrategyParsing:
    def test_parse_well_formed_output(self):
        text = """\
===STRATEGY 1===
Name: Direct Approach
Description: Follow the skill directly
Approach:
1. Read the code
2. Apply rules
3. Report findings

===STRATEGY 2===
Name: Security First
Description: Focus on security issues
Approach:
1. Check for injections
2. Check auth
"""
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(text)

        assert len(strategies) == 2
        assert strategies[0].name == "Direct Approach"
        assert strategies[0].description == "Follow the skill directly"
        assert "Read the code" in strategies[0].approach
        assert strategies[1].name == "Security First"

    def test_parse_missing_fields_uses_defaults(self):
        text = """\
===STRATEGY 1===
Description: Only a description
Approach:
Do something
"""
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(text)

        assert len(strategies) == 1
        assert strategies[0].name == "Strategy 1"

    def test_parse_empty_returns_empty(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies("No strategies here.")
        assert strategies == []

    def test_strategy_ids_are_sequential(self):
        text = """\
===STRATEGY 1===
Name: A
Description: A
Approach:
A

===STRATEGY 2===
Name: B
Description: B
Approach:
B

===STRATEGY 3===
Name: C
Description: C
Approach:
C
"""
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(text)

        assert [s.id for s in strategies] == [1, 2, 3]
