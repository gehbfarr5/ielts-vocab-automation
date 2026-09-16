import pytest
from test_anki import FakeAnki

from ielts_vocab.adoption import adopt_notes
from ielts_vocab.anki import FIELDS, MODEL


class Legacy(FakeAnki):
    def __init__(self):
        super().__init__()
        f = dict.fromkeys(FIELDS, "")
        f.update(
            EntryID="legacy", Lemma="conceal", CoreCountKey="en:conceal", PrimaryMeaning="隐瞒"
        )
        self.notes[1] = f

    def note(self, nid):
        return dict(
            noteId=nid,
            modelName=MODEL,
            cards=[10],
            fields={k: {"value": v} for k, v in self.notes[nid].items()},
        )

    def call(self, action, **kwargs):
        if action == "getReviewsOfCards":
            return {"10": []}
        return super().call(action, **kwargs)


def test_adoption_is_idempotent_and_counts_inventory(store, tmp_path):
    a = Legacy()
    specs = [dict(note_id=1, part_of_speech="verb", sense_label="hide")]
    for _ in range(2):
        adopt_notes(store, a, specs, tmp_path / "intent.json", "Asia/Shanghai", 4)
    assert a.adds == 0
    assert store.usage("2099-01-01") == {"cores": 1, "cards": 1, "contexts": 0}
    assert store.db.execute("SELECT count(*) FROM mappings").fetchone()[0] == 1
    a.notes[1]["PrimaryMeaning"] = "用户新改"
    with pytest.raises(ValueError, match="changed"):
        adopt_notes(store, a, specs, tmp_path / "intent.json", "Asia/Shanghai", 4)
