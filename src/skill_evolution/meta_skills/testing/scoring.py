"""Structural scoring functions for meta-skills.

V1 uses deterministic metrics only (format compliance, placeholder
presence, output structure) to avoid evaluation circularity.
"""

from __future__ import annotations

import re
from typing import Callable, Protocol

from skill_evolution.meta_skills.testing.models import EvalCase, ScoreResult, SuiteResult


class MetaSkillScorer(Protocol):
    """Scores a meta-skill's output against an EvalCase."""

    def score(self, case: EvalCase, output: str) -> ScoreResult: ...


class StrategyGenerationScorer:
    """Structural scorer for strategy_generation meta-skill output.

    Checks: strategy count matches k, each has a name/approach,
    strategies are textually distinct, no empty blocks.
    """

    def score(self, case: EvalCase, output: str) -> ScoreResult:
        expected_k = case.expected.get("k", 4)
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        blocks = re.split(r"===STRATEGY\s*\d+\s*===", output)
        strategies = [b.strip() for b in blocks[1:] if b.strip()]
        actual_k = len(strategies)

        checks["count_matches"] = actual_k == expected_k
        if not checks["count_matches"]:
            reasons.append(f"Expected {expected_k} strategies, got {actual_k}")

        named = 0
        has_approach = 0
        non_empty = 0
        for block in strategies:
            if re.search(r"Name:\s*\S", block):
                named += 1
            if re.search(r"Approach:", block):
                has_approach += 1
            if len(block) > 20:
                non_empty += 1

        checks["all_named"] = named == actual_k and actual_k > 0
        checks["all_have_approach"] = has_approach == actual_k and actual_k > 0
        checks["all_non_empty"] = non_empty == actual_k and actual_k > 0

        if not checks["all_named"]:
            reasons.append(f"Only {named}/{actual_k} strategies have names")
        if not checks["all_have_approach"]:
            reasons.append(f"Only {has_approach}/{actual_k} strategies have approach sections")

        if actual_k >= 2:
            distinct_pairs = 0
            total_pairs = 0
            for i in range(actual_k):
                for j in range(i + 1, actual_k):
                    total_pairs += 1
                    overlap = _jaccard_similarity(strategies[i], strategies[j])
                    if overlap < 0.7:
                        distinct_pairs += 1
            checks["strategies_distinct"] = distinct_pairs == total_pairs
            if not checks["strategies_distinct"]:
                reasons.append(
                    f"{total_pairs - distinct_pairs}/{total_pairs} strategy pairs are too similar"
                )
        else:
            checks["strategies_distinct"] = actual_k <= 1

        passed_count = sum(checks.values())
        total_checks = len(checks)
        score = passed_count / total_checks if total_checks > 0 else 0.0

        return ScoreResult(
            case_id=case.id,
            score=score,
            passed=score >= 0.8,
            reason="; ".join(reasons) if reasons else "All structural checks passed",
            details=checks,
        )


class TrajectoryComparisonScorer:
    """Structural scorer for trajectory_comparison meta-skill output.

    Checks: signals are present, categories are valid, confidence
    in range, descriptions non-empty, evidence provided.
    """

    VALID_CATEGORIES = {"missing_knowledge", "wrong_approach", "edge_case", "efficiency"}

    def score(self, case: EvalCase, output: str) -> ScoreResult:
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        if "===NO_SIGNALS===" in output:
            expect_signals = case.expected.get("expect_signals", True)
            checks["no_signals_correct"] = not expect_signals
            if expect_signals:
                reasons.append("Output says NO_SIGNALS but signals were expected")
            score = 1.0 if checks["no_signals_correct"] else 0.0
            return ScoreResult(
                case_id=case.id,
                score=score,
                passed=score >= 0.8,
                reason=reasons[0] if reasons else "Correctly returned no signals",
                details=checks,
            )

        blocks = re.split(r"===SIGNAL\s*\d+\s*===", output)
        signals = [b.strip() for b in blocks[1:] if b.strip()]

        min_signals = case.expected.get("min_signals", 1)
        checks["has_signals"] = len(signals) >= min_signals
        if not checks["has_signals"]:
            reasons.append(f"Expected >= {min_signals} signals, got {len(signals)}")

        valid_categories = 0
        valid_confidence = 0
        has_description = 0
        has_evidence = 0
        valid_affects = 0

        for block in signals:
            cat_match = re.search(r"Category:\s*(\S+)", block)
            if cat_match and cat_match.group(1).lower() in self.VALID_CATEGORIES:
                valid_categories += 1

            conf_match = re.search(r"Confidence:\s*([\d.]+)", block)
            if conf_match:
                try:
                    conf = float(conf_match.group(1))
                    if 0.0 <= conf <= 1.0:
                        valid_confidence += 1
                except ValueError:
                    pass

            if re.search(r"Description:\s*\S", block):
                has_description += 1
            if re.search(r"Evidence:\s*\S", block):
                has_evidence += 1

            aff_match = re.search(r"Affects:\s*(\S+)", block)
            if aff_match and aff_match.group(1).lower() in ("body", "appendix"):
                valid_affects += 1

        n = len(signals) or 1
        checks["valid_categories"] = valid_categories == len(signals) and len(signals) > 0
        checks["valid_confidence"] = valid_confidence == len(signals) and len(signals) > 0
        checks["has_descriptions"] = has_description == len(signals) and len(signals) > 0
        checks["has_evidence"] = has_evidence == len(signals) and len(signals) > 0
        checks["valid_affects"] = valid_affects == len(signals) and len(signals) > 0

        if not checks["valid_categories"]:
            reasons.append(f"Only {valid_categories}/{n} signals have valid categories")
        if not checks["valid_confidence"]:
            reasons.append(f"Only {valid_confidence}/{n} signals have valid confidence [0,1]")
        if not checks["has_descriptions"]:
            reasons.append(f"Only {has_description}/{n} signals have descriptions")

        passed_count = sum(checks.values())
        total_checks = len(checks)
        score = passed_count / total_checks if total_checks > 0 else 0.0

        return ScoreResult(
            case_id=case.id,
            score=score,
            passed=score >= 0.8,
            reason="; ".join(reasons) if reasons else "All structural checks passed",
            details=checks,
        )


_SCORERS: dict[str, MetaSkillScorer] = {
    "strategy_generation": StrategyGenerationScorer(),
    "trajectory_comparison": TrajectoryComparisonScorer(),
}


def get_scorer(meta_skill_name: str) -> MetaSkillScorer:
    """Get the scorer for a meta-skill by name."""
    if meta_skill_name not in _SCORERS:
        available = ", ".join(sorted(_SCORERS.keys()))
        raise KeyError(
            f"No scorer for meta-skill {meta_skill_name!r}. Available: {available}"
        )
    return _SCORERS[meta_skill_name]


def score_meta_skill(
    meta_skill_name: str,
    cases: list[EvalCase],
    output_fn: Callable[[EvalCase], str],
) -> SuiteResult:
    """Run a full test suite against a meta-skill's output.

    Args:
        meta_skill_name: Which meta-skill to score
        cases: Test cases to run
        output_fn: Function that takes an EvalCase and returns the
                   meta-skill's output string for that case
    """
    scorer = get_scorer(meta_skill_name)
    results: list[ScoreResult] = []

    for case in cases:
        output = output_fn(case)
        result = scorer.score(case, output)
        results.append(result)

    passed = sum(1 for r in results if r.passed)
    mean_score = sum(r.score for r in results) / len(results) if results else 0.0

    return SuiteResult(
        meta_skill=meta_skill_name,
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        mean_score=mean_score,
        results=results,
    )


def _jaccard_similarity(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a and not words_b:
        return 1.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0
