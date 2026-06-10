"""Tests for bridge_auto_respond.py — regression coverage for classify_request,
neutral default templates, template-pack loading, and the intel-analyzer
example pack in examples/intel_analyzer_bridge/."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
META_SKILLS_DIR = ROOT / "src" / "skill_evolution" / "meta_skills"
INTEL_PACK_PATH = ROOT / "examples" / "intel_analyzer_bridge" / "templates.py"

sys.path.insert(0, str(SCRIPTS_DIR))
import bridge_auto_respond as bar  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from skill_evolution.core.explorer import Explorer  # noqa: E402

# ── helpers ──────────────────────────────────────────────────────────────────

def _load_meta_skill_text(name: str) -> str:
    """Load raw text of a meta-skill markdown file."""
    path = META_SKILLS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def _make_request(system: str, user_content: str = "") -> dict:
    return {
        "system": system,
        "messages": [{"content": user_content}],
    }


@pytest.fixture(scope="module")
def intel_pack() -> bar.TemplatePack:
    """The intel-analyzer example pack, loaded via the public loader."""
    return bar.load_templates(str(INTEL_PACK_PATH))


# ── 1. classify_request: all 5 types via real meta-skill prompts ────────────

class TestClassifyWithRealMetaSkills:
    """Verify classify_request identifies all 5 types using actual meta-skill
    system prompts loaded from src/skill_evolution/meta_skills/*.md."""

    def test_strategy_generation(self):
        system = _load_meta_skill_text("strategy_generation")
        req = _make_request(system)
        assert bar.classify_request(req) == "strategy_generation"

    def test_strategy_generation_via_user_message(self):
        req = _make_request(
            system="You help with strategies.",
            user_content="Generate exactly 3 diverse strategies for this task.",
        )
        assert bar.classify_request(req) == "strategy_generation"

    def test_comparator(self):
        system = _load_meta_skill_text("trajectory_comparison")
        req = _make_request(system)
        assert bar.classify_request(req) == "comparator"

    def test_patcher(self):
        system = _load_meta_skill_text("skill_patch")
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_auditor(self):
        system = _load_meta_skill_text("skill_audit")
        req = _make_request(system)
        assert bar.classify_request(req) == "auditor"

    def test_executor(self):
        system = "You are an AI agent executing a task. Follow the strategy."
        req = _make_request(system)
        assert bar.classify_request(req) == "executor"

    def test_executor_via_execution_trace(self):
        system = "Produce an execution trace of your work."
        req = _make_request(system)
        assert bar.classify_request(req) == "executor"


# ── 2. Patcher must NOT be misclassified as comparator ──────────────────────

class TestPatcherNotMisclassified:
    """Regression: the patcher system prompt contains 'delta signals' which
    previously matched the comparator check.  Patcher must win."""

    def test_patcher_with_real_prompt(self):
        system = _load_meta_skill_text("skill_patch")
        assert "delta signal" in system.lower(), (
            "Precondition: patcher prompt must mention 'delta signal'"
        )
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_patcher_with_delta_signal_and_patch_keyword(self):
        system = "Apply patch based on delta signals from comparison."
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_comparator_requires_no_patch_keyword(self):
        system = "Analyze delta signals between trajectories."
        req = _make_request(system)
        assert bar.classify_request(req) == "comparator"

    def test_precision_skill_editor_routes_to_patcher(self):
        system = "You are a precision skill editor."
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"

    def test_updated_body_marker_routes_to_patcher(self):
        system = "Output in ===UPDATED_BODY=== format."
        req = _make_request(system)
        assert bar.classify_request(req) == "patcher"


# ── 3. Neutral DEFAULT_STRATEGY parses into 3 valid strategies ──────────────

class TestDefaultStrategyParsing:
    """The neutral DEFAULT_STRATEGY must use ===STRATEGY N=== markers and
    parse into exactly 3 Strategy objects via Explorer._parse_strategies."""

    def test_has_strategy_markers(self):
        for i in range(1, 4):
            assert f"===STRATEGY {i}===" in bar.DEFAULT_STRATEGY

    def test_parses_into_three_strategies(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        assert len(strategies) == 3

    def test_parsed_strategies_have_names(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        for s in strategies:
            assert s.name, f"Strategy {s.id} has no name"
            assert s.name != f"Strategy {s.id}", (
                f"Strategy {s.id} fell back to default name"
            )

    def test_parsed_strategies_have_descriptions(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        for s in strategies:
            assert s.description, f"Strategy {s.id} has no description"

    def test_parsed_strategies_have_approaches(self):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(bar.DEFAULT_STRATEGY)
        for s in strategies:
            assert s.approach, f"Strategy {s.id} has no approach"


# ── 4. Template-pack loading ─────────────────────────────────────────────────

class TestTemplatePackLoading:
    def test_default_pack_is_neutral(self):
        pack = bar.load_templates(None)
        assert pack.name == "neutral-demo"
        assert pack.strategy_templates == {}
        assert pack.topic_patterns == ()
        assert pack.default_strategy == bar.DEFAULT_STRATEGY

    def test_load_from_file_path(self, intel_pack: bar.TemplatePack):
        assert intel_pack.name == "intel-analyzer"
        assert len(intel_pack.strategy_templates) == 7

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            bar.load_templates(str(tmp_path / "nonexistent.py"))

    def test_missing_module_raises(self):
        with pytest.raises(ImportError):
            bar.load_templates("definitely_not_a_real_module_xyz")

    def test_partial_pack_falls_back_to_defaults(self, tmp_path: Path):
        pack_file = tmp_path / "partial.py"
        pack_file.write_text(
            'PACK_NAME = "partial"\nDEFAULT_STRATEGY = "custom strategy"\n',
            encoding="utf-8",
        )
        pack = bar.load_templates(str(pack_file))
        assert pack.name == "partial"
        assert pack.default_strategy == "custom strategy"
        # Unspecified attributes fall back to neutral defaults
        assert pack.comparator_response == bar.COMPARATOR_RESPONSE
        assert pack.auditor_response == bar.AUDITOR_RESPONSE


# ── 5. Topic extraction is pack-driven ───────────────────────────────────────

class TestTopicExtraction:
    def test_no_patterns_returns_general(self):
        req = _make_request("sys", "TeraWulf duplicate dedup content")
        assert bar.extract_task_topic(req) == "general"

    def test_empty_messages_returns_general(self):
        assert bar.extract_task_topic({"messages": []}) == "general"

    @pytest.mark.parametrize("content,expected", [
        ("TeraWulf acquisition reported twice", "dedup"),
        ("EngineAI video from Reddit", "credibility"),
        ("editorial pieces score too high", "opinion_vs_event"),
        ("评分是简单相加导致区分度差", "scoring_formula"),
        ("low-score noise items remain", "noise_floor"),
        ("coordinated state media narratives", "source_independence"),
        ("SpaceX launch is missing from report", "priority_events"),
    ])
    def test_intel_pack_topics(
        self, intel_pack: bar.TemplatePack, content: str, expected: str
    ):
        req = _make_request("sys", content)
        assert bar.extract_task_topic(req, intel_pack.topic_patterns) == expected

    def test_first_matching_pattern_wins(self):
        patterns = (("a", ("foo",)), ("b", ("foo", "bar")))
        req = _make_request("sys", "foo bar")
        assert bar.extract_task_topic(req, patterns) == "a"


# ── 6. Response generators honor the pack ────────────────────────────────────

class TestResponseGenerators:
    def test_strategy_unknown_topic_uses_default(self):
        pack = bar.TemplatePack()
        req = _make_request("sys", "something unrelated")
        assert bar.generate_strategy_response(req, pack) == pack.default_strategy

    def test_strategy_known_topic_uses_template(self, intel_pack: bar.TemplatePack):
        req = _make_request("sys", "TeraWulf duplicates")
        out = bar.generate_strategy_response(req, intel_pack)
        assert out == intel_pack.strategy_templates["dedup"]

    def test_executor_formats_strategy_name_and_topic(self):
        pack = bar.TemplatePack()
        req = _make_request(
            "## Strategy to Follow\nMy Great Strategy\n\nDetails here.", "task"
        )
        out = bar.generate_executor_response(req, pack)
        assert "My Great Strategy" in out
        assert "{strategy_name}" not in out
        assert "{topic}" not in out

    def test_comparator_patcher_auditor_pass_through(self, intel_pack: bar.TemplatePack):
        req = _make_request("sys")
        assert bar.generate_comparator_response(req, intel_pack) == intel_pack.comparator_response
        assert bar.generate_patcher_response(req, intel_pack) == intel_pack.patcher_response
        assert bar.generate_auditor_response(req, intel_pack) == intel_pack.auditor_response

    def test_neutral_comparator_is_format_valid(self):
        pack = bar.TemplatePack()
        assert "===SIGNAL 1===" in pack.comparator_response
        assert "===END===" in pack.comparator_response

    def test_neutral_patcher_is_format_valid(self):
        pack = bar.TemplatePack()
        assert "===UPDATED_BODY===" in pack.patcher_response
        assert "===CHANGELOG===" in pack.patcher_response

    def test_neutral_auditor_is_format_valid(self):
        pack = bar.TemplatePack()
        assert "===CHECK:" in pack.auditor_response
        assert "===OVERALL===" in pack.auditor_response


# ── 7. Intel example pack: all 7 topic templates parse correctly ────────────

EXPECTED_TOPICS = [
    "dedup",
    "credibility",
    "opinion_vs_event",
    "scoring_formula",
    "noise_floor",
    "source_independence",
    "priority_events",
]


class TestIntelPackTemplates:
    """Each of the 7 intel-analyzer topic templates must be present in the
    example pack and parse into exactly 3 strategies via Explorer."""

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_exists(self, intel_pack: bar.TemplatePack, topic: str):
        assert topic in intel_pack.strategy_templates

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_has_strategy_markers(self, intel_pack: bar.TemplatePack, topic: str):
        text = intel_pack.strategy_templates[topic]
        for i in range(1, 4):
            assert f"===STRATEGY {i}===" in text, (
                f"Topic '{topic}' missing ===STRATEGY {i}=== marker"
            )

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_parses_into_three_strategies(
        self, intel_pack: bar.TemplatePack, topic: str
    ):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(intel_pack.strategy_templates[topic])
        assert len(strategies) == 3, (
            f"Topic '{topic}' parsed into {len(strategies)} strategies, expected 3"
        )

    @pytest.mark.parametrize("topic", EXPECTED_TOPICS)
    def test_template_strategies_have_names(self, intel_pack: bar.TemplatePack, topic: str):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(intel_pack.strategy_templates[topic])
        for s in strategies:
            assert s.name and s.name != f"Strategy {s.id}", (
                f"Topic '{topic}' strategy {s.id} missing a real name"
            )

    def test_no_unexpected_templates(self, intel_pack: bar.TemplatePack):
        assert set(intel_pack.strategy_templates.keys()) == set(EXPECTED_TOPICS)

    def test_intel_default_strategy_parses(self, intel_pack: bar.TemplatePack):
        explorer = Explorer.__new__(Explorer)
        strategies = explorer._parse_strategies(intel_pack.default_strategy)
        assert len(strategies) == 3


# ── 8. Generic bridge mechanics: pending list and response write ────────────

class TestBridgeMechanics:
    @pytest.fixture()
    def bridge_dirs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        req_dir = tmp_path / "requests"
        resp_dir = tmp_path / "responses"
        monkeypatch.setattr(bar, "BRIDGE_DIR", tmp_path)
        monkeypatch.setattr(bar, "REQUEST_DIR", req_dir)
        monkeypatch.setattr(bar, "RESPONSE_DIR", resp_dir)
        return req_dir, resp_dir

    def test_list_pending_skips_answered_and_invalid(self, bridge_dirs):
        req_dir, resp_dir = bridge_dirs
        bar.setup()
        (req_dir / "a.json").write_text('{"id": "a"}', encoding="utf-8")
        (req_dir / "b.json").write_text('{"id": "b"}', encoding="utf-8")
        (req_dir / "c.json").write_text("not json", encoding="utf-8")
        (resp_dir / "b.json").write_text('{"content": "done"}', encoding="utf-8")

        pending = bar.list_pending()
        assert [p["id"] for p in pending] == ["a"]

    def test_write_response_envelope(self, bridge_dirs):
        import json

        _, resp_dir = bridge_dirs
        bar.setup()
        bar.write_response("req-1", "hello")

        data = json.loads((resp_dir / "req-1.json").read_text(encoding="utf-8"))
        assert data["content"] == "hello"
        assert data["model"] == "bridge-agent"
        assert data["stop_reason"] == "end_turn"
        assert not (resp_dir / "req-1.tmp").exists()
