"""RegressionGate — blocks promotion when any test score regresses.

The gate compares candidate scores against baseline scores:
- PASS: no test regresses AND at least one improves
- PASS (no change): no test regresses, none improve (tie)
- FAIL: any test score drops below baseline
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateVerdict:
    """Result of running the regression gate."""

    passed: bool
    improved: list[str] = field(default_factory=list)
    regressed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    new_cases: list[str] = field(default_factory=list)
    summary: str = ""


def check_regression(
    baseline: dict[str, float],
    candidate: dict[str, float],
    tolerance: float = 0.0,
) -> GateVerdict:
    """Compare candidate scores against baseline.

    Args:
        baseline: Score map from the current accepted version
        candidate: Score map from the proposed new version
        tolerance: Allowed score decrease before counting as regression
                   (e.g., 0.05 allows a 5% drop)

    Returns:
        GateVerdict with pass/fail and per-case breakdown
    """
    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []
    new_cases: list[str] = []

    all_keys = set(baseline) | set(candidate)

    for key in sorted(all_keys):
        if key not in baseline:
            new_cases.append(key)
            continue
        if key not in candidate:
            regressed.append(key)
            continue

        base_score = baseline[key]
        cand_score = candidate[key]
        delta = cand_score - base_score

        if delta < -tolerance:
            regressed.append(key)
        elif delta > tolerance:
            improved.append(key)
        else:
            unchanged.append(key)

    passed = len(regressed) == 0

    parts: list[str] = []
    if regressed:
        parts.append(f"{len(regressed)} regressed")
    if improved:
        parts.append(f"{len(improved)} improved")
    if unchanged:
        parts.append(f"{len(unchanged)} unchanged")
    if new_cases:
        parts.append(f"{len(new_cases)} new")
    summary = f"{'PASS' if passed else 'FAIL'}: {', '.join(parts)}"

    return GateVerdict(
        passed=passed,
        improved=improved,
        regressed=regressed,
        unchanged=unchanged,
        new_cases=new_cases,
        summary=summary,
    )
