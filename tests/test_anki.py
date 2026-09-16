import copy

import pytest
from conftest import open_day, put_candidate

from ielts_vocab.anki import AnkiError, execute, first_answer, make_plan, render


class FakeAnki:
    def __init__(self):
        self.notes = {}
        self.adds = 0
        self.fail_after_add = False

    def guard(self):
        pass

    def find_entry(self, entry):
        return [nid for nid, n in self.notes.items() if n["EntryID"] == entry]

    def fields(self, nid):
        return copy.deepcopy(self.notes[nid])

    def note(self, nid):
        return {
            "cards": [
                nid * 10 + i for i in range(3) if i == 0 or self.notes[nid][f"Context{i}Prompt"]
            ]
        }

    def call(self, action, **params):
        if action == "addNote":
            self.adds += 1
            self.notes[self.adds] = copy.deepcopy(params["note"]["fields"])
            if self.fail_after_add:
                self.fail_after_add = False
                raise TimeoutError("Response lost after durable write")
            return self.adds
        if action == "cardsInfo":
            return [{"cardId": c, "ord": c % 10} for c in params["cards"]]
        if action == "updateNoteFields":
            self.notes[params["note"]["id"]].update(params["note"]["fields"])
            return None
        raise AssertionError(action)


def test_first_actual_answer_not_manual_or_unsorted():
    assert (
        first_answer(
            [
                {"id": 1, "ease": 0, "type": 4},
                {"id": 30, "ease": 3, "type": 1},
                {"id": 20, "ease": 1, "type": 0},
                {"id": 0, "ease": 0, "type": 5},
            ]
        )
        == 20
    )
    assert first_answer([{"id": 1, "ease": 0, "type": 4}]) is None


def test_html_is_escaped(candidate):
    assert (
        "&lt;script&gt;"
        in render(candidate.model_copy(update={"lemma": "<script>"}))["RecognitionPrompt"]
    )


def test_uncertain_add_recovery_preserves_single_note(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    a = FakeAnki()
    open_day(store)
    plan = make_plan(store, a, c, "IELTS")
    store.reserve("op", c["id"], c["core_key"], "Recognition", False, "2026-09-16", plan)
    a.fail_after_add = True
    with pytest.raises(TimeoutError):
        execute(store, a, "op")
    execute(store, a, "op")
    assert a.adds == 1
    assert store.db.execute("SELECT state FROM operations").fetchone()[0] == "written"


def test_new_sense_same_note_and_user_edit_conflict(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    a = FakeAnki()
    open_day(store)
    plan = make_plan(store, a, c, "IELTS")
    store.reserve("op", c["id"], c["core_key"], "Recognition", False, "2026-09-16", plan)
    execute(store, a, "op")
    c2 = put_candidate(
        store, tmp_path, image_bytes, candidate.model_copy(update={"sense_label": "assert firmly"})
    )
    p2 = make_plan(store, a, c2, "IELTS")
    assert p2["kind"] == "context" and p2["slot"] == "Context 1" and p2["note_id"] == 1
    store.reserve("op2", c2["id"], c2["core_key"], "Context 1", True, "2026-09-16", p2)
    a.notes[1]["UserNotes"] = "Keep my personal note"
    execute(store, a, "op2")
    assert a.adds == 1 and a.notes[1]["UserNotes"] == "Keep my personal note"
    assert a.notes[1]["PrimaryMeaning"] == candidate.context_meaning_zh
    a.notes[1]["PrimaryMeaning"] = "User changed the managed gloss"
    with pytest.raises(AnkiError, match="edited outside"):
        make_plan(store, a, c2, "IELTS")


def test_readback_detects_silent_update_failure(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    a = FakeAnki()
    open_day(store)
    plan = make_plan(store, a, c, "IELTS")
    store.reserve("op", c["id"], c["core_key"], "Recognition", False, "2026-09-16", plan)
    execute(store, a, "op")
    c2 = put_candidate(
        store, tmp_path, image_bytes, candidate.model_copy(update={"sense_label": "assert"})
    )
    p2 = make_plan(store, a, c2, "IELTS")
    store.reserve("op2", c2["id"], c2["core_key"], "Context 1", True, "2026-09-16", p2)
    original = a.call
    a.call = lambda action, **params: (
        None if action == "updateNoteFields" else original(action, **params)
    )
    with pytest.raises(AnkiError, match="readback"):
        execute(store, a, "op2")
    assert store.usage("2026-09-16")["cards"] == 2
