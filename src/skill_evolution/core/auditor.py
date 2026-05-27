"""Independent Skill Auditor — reviews evolved skills for quality issues.

Inspired by SkillEvolver's independent audit agent.
This is run by a SEPARATE LLM call to avoid self-confirmation bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from skill_evolution.llm.base import LLMBackend
from skill_evolution.meta_skills.loader import load_meta_skill
from skill_evolution.skill.schema import Skill


class AuditSeverity(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class AuditFinding:
    """A single finding from the audit."""

    check: str  # Which check found this
    severity: AuditSeverity
    description: str
    suggestion: str = ""


@dataclass
class AuditReport:
    """Complete audit report for a skill."""

    findings: list[AuditFinding]
    overall: AuditSeverity
    summary: str

    @property
    def passed(self) -> bool:
        return self.overall != AuditSeverity.FAIL


_FALLBACK_PROMPT = """\
You are an independent skill quality auditor. You review AI agent skill documents \
for potential problems. You have NOT seen the evolution process — you only see the \
skill document and must assess it purely on its own merits.

Run these checks:

1. **Overfitting**: Does the skill contain rules that are too specific to individual \
   tasks rather than generalizable patterns?
2. **Hardcoding**: Does the skill hardcode specific values, paths, names, or assumptions \
   that should be parameterized?
3. **Silent Bypass**: Does the skill contain instructions that an agent might silently \
   ignore because they're contradictory or unclear?
4. **Consistency**: Are the rules internally consistent? Do any sections contradict others?
5. **Generalizability**: Would this skill work across diverse instances of its stated domain, \
   or only in narrow scenarios?

Output format:
===CHECK: <check_name>===
Severity: PASS | WARNING | FAIL
Description: <what you found>
Suggestion: <how to fix it, if applicable>

===CHECK: ...===
...

===OVERALL===
Severity: PASS | WARNING | FAIL
Summary: <1-2 sentence overall assessment>
"""

_OUTPUT_FORMAT = """
Output format:
===CHECK: <check_name>===
Severity: PASS | WARNING | FAIL
Description: <what you found>
Suggestion: <how to fix it, if applicable>

===CHECK: ...===
...

===OVERALL===
Severity: PASS | WARNING | FAIL
Summary: <1-2 sentence overall assessment>
"""


class Auditor:
    """Reviews evolved skills for overfitting, hardcoding, and other quality issues."""

    def __init__(self, llm: LLMBackend, workspace: Path | None = None):
        self.llm = llm
        base_prompt = load_meta_skill("skill_audit", _FALLBACK_PROMPT, workspace)
        self._system_prompt = base_prompt + _OUTPUT_FORMAT

    async def audit(self, skill: Skill) -> AuditReport:
        """Run an independent audit on a skill document."""
        prompt = f"""\
## Skill: {skill.metadata.name}
## Domain: {skill.metadata.domain}
## Version: {skill.metadata.version}

### Body
{skill.body}

### Appendix
{skill.appendix if skill.appendix else "(empty)"}

Audit this skill document."""

        resp = await self.llm.ask(prompt=prompt, system=self._system_prompt, temperature=0.3)
        return self._parse_report(resp.content)

    def _parse_report(self, text: str) -> AuditReport:
        """Parse audit output into an AuditReport."""
        findings = []
        overall_severity = AuditSeverity.PASS
        summary = ""

        # Parse individual checks
        check_blocks = text.split("===CHECK:")
        for block in check_blocks[1:]:
            if "===OVERALL===" in block:
                block = block[:block.index("===OVERALL===")]

            check_name = block.split("===")[0].strip()
            severity = AuditSeverity.PASS
            description = ""
            suggestion = ""

            for line in block.split("\n"):
                stripped = line.strip()
                if stripped.startswith("Severity:"):
                    raw = stripped[len("Severity:"):].strip().upper()
                    if "FAIL" in raw:
                        severity = AuditSeverity.FAIL
                    elif "WARNING" in raw:
                        severity = AuditSeverity.WARNING
                    else:
                        severity = AuditSeverity.PASS
                elif stripped.startswith("Description:"):
                    description = stripped[len("Description:"):].strip()
                elif stripped.startswith("Suggestion:"):
                    suggestion = stripped[len("Suggestion:"):].strip()

            findings.append(AuditFinding(
                check=check_name,
                severity=severity,
                description=description,
                suggestion=suggestion,
            ))

        # Parse overall assessment
        if "===OVERALL===" in text:
            overall_block = text.split("===OVERALL===")[1]
            for line in overall_block.split("\n"):
                stripped = line.strip()
                if stripped.startswith("Severity:"):
                    raw = stripped[len("Severity:"):].strip().upper()
                    if "FAIL" in raw:
                        overall_severity = AuditSeverity.FAIL
                    elif "WARNING" in raw:
                        overall_severity = AuditSeverity.WARNING
                elif stripped.startswith("Summary:"):
                    summary = stripped[len("Summary:"):].strip()

        return AuditReport(
            findings=findings,
            overall=overall_severity,
            summary=summary,
        )
