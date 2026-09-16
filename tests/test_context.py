import json
import subprocess

from ielts_vocab.analysis import codex_analyze
from ielts_vocab.context import relevant, restrict_history
from ielts_vocab.models import Analysis


def line(text, mark):
    return {"text": text, "marked_spans": [{"text": mark}]}


def test_retrieval_requires_marked_word_not_neighbour_or_substring():
    lines = [line("The art concealed a dangling object.", "concealed dangling")]
    assert relevant("conceal", [], lines)
    assert relevant("dangle", [], lines)
    assert not relevant("art", [], lines)
    assert not relevant("concealment", [], lines)
    assert not relevant("art", [], [line("Start now.", "Start")])


def test_phrase_anchor_and_previously_observed_irregular_surface():
    assert relevant(
        "skeleton in the cupboard", [], [line("A skeleton in the cupboard.", "cupboard")]
    )
    assert not relevant("skeleton in the cupboard", [], [line("A skeleton in the cupboard.", "in")])
    assert relevant("go", ["went"], [line("She went home.", "went")])
    assert not relevant("go", [], [line("She went home.", "went")])


def test_outbound_history_is_minimized_and_input_unmodified(tmp_path, monkeypatch, candidate):
    evidence = {
        "ocr_lines": [line("We maintain the system.", "maintain")],
        "known_surfaces": {"maintain": ["maintained"], "private": ["PRIVATE_SURFACE"]},
        "known_senses": [
            {"lemma": "maintain", "meaning": "keep"},
            {"lemma": "private", "meaning": "PRIVATE_MEANING"},
        ],
        "anki_review_history": {
            "observed_at": 123,
            "entries": [
                {
                    "lemma": lemma,
                    "cards": [{"card_id": 987654, "interval": 8, "reps": 4, "lapses": 1}],
                    "recent_reviews": {"987654": [{"secret": "RAW_REVIEW"}]},
                }
                for lemma in ("maintain", "private")
            ],
        },
    }

    def run(command, **kwargs):
        assert command[command.index("--model") + 1] == "gpt-5.6-sol"
        assert 'model_reasoning_effort="medium"' in command
        for secret in (
            "PRIVATE_SURFACE",
            "PRIVATE_MEANING",
            "RAW_REVIEW",
            "987654",
            '"lemma": "private"',
        ):
            assert secret not in kwargs["input"]
        (tmp_path / "result.json").write_text(
            Analysis(candidates=[candidate], notes="").model_dump_json()
        )
        return subprocess.CompletedProcess(
            command, 0, "", "model: gpt-5.6-sol\nreasoning effort: medium\n"
        )

    monkeypatch.setattr(subprocess, "run", run)
    codex_analyze(None, evidence, tmp_path, allow_cloud=True)
    assert len(evidence["anki_review_history"]["entries"]) == 2
    assert len(restrict_history(evidence)["anki_review_history"]["entries"]) == 1
    audit = json.loads((tmp_path / "analyzer-call.json").read_text())
    assert audit["observed_cli"]["model"] == "gpt-5.6-sol"
