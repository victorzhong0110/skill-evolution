"""Input guards against parser-delimiter injection.

The Explorer/Comparator/Patcher/Auditor prompts ask the LLM to emit sections
fenced by ``===TOKEN===`` delimiters, and the parsers split on those tokens.
Any *input* text (task descriptions, skill body/appendix) that already contains
such a token would corrupt the parse — e.g. a task containing
``===UPDATED_BODY===`` could replace the patched skill with attacker-chosen
content. Inputs are validated at the pipeline boundary and rejected loudly;
silent escaping would hide the problem and alter user content.
"""

from __future__ import annotations

import re

# Exact tokens the section parsers split on. Several parsers split on the bare
# prefix (e.g. ``text.split("===SIGNAL")``), so the prefix alone is dangerous —
# no closing ``===`` is required for a match.
RESERVED_DELIMITER_RE = re.compile(
    r"===\s*(?:UPDATED_BODY|UPDATED_APPENDIX|CHANGELOG|SIGNAL|STRATEGY|CHECK|OVERALL|NO_SIGNALS|END)\b"
)


def find_reserved_delimiters(text: str) -> list[str]:
    """Return every reserved parser delimiter occurring in *text*."""
    return [m.group(0) for m in RESERVED_DELIMITER_RE.finditer(text)]


def ensure_prompt_safe(text: str, source: str) -> None:
    """Raise ValueError if *text* contains reserved parser delimiters.

    Args:
        text: Untrusted input destined for an LLM prompt.
        source: Human-readable origin used in the error message.
    """
    hits = find_reserved_delimiters(text)
    if hits:
        raise ValueError(
            f"{source} contains reserved parser delimiter(s) {sorted(set(hits))}; "
            "these would corrupt section parsing (prompt-injection surface). "
            "Remove or rephrase them before evolving."
        )
