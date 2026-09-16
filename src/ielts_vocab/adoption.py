"""Explicitly reviewed legacy notes join the ledger without recreating cards."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .anki import MODEL, first_answer
from .models import digest, lemma_key, study_day


def adopt_notes(store, anki, specs, backup: Path, timezone_name, rollover_hour):
    anki.guard()
    notes = [anki.note(spec["note_id"]) for spec in specs]
    if any(note["modelName"] != MODEL for note in notes):
        raise ValueError("Only reviewed managed notes can be adopted")
    # Immutable intent permits resuming a partial field update safely.
    if not backup.exists():
        backup.write_text(
            json.dumps({"specs": specs, "notes": notes}, ensure_ascii=False, indent=2)
        )
        backup.chmod(0o600)
    intent = json.loads(backup.read_text())
    if intent["specs"] != specs:
        raise ValueError("Adoption intent differs")
    for spec, note, original in zip(specs, notes, intent["notes"], strict=True):
        nid = note["noteId"]
        key = lemma_key(note["fields"]["Lemma"]["value"])
        entry = digest(key)[:32]
        sense = digest([key, spec["part_of_speech"].casefold(), spec["sense_label"].casefold()])[
            :24
        ]
        if len(note["cards"]) != 1:
            raise ValueError("Legacy Context cards require explicit slot mapping")
        card = anki.call("cardsInfo", cards=note["cards"])[0]
        if card["ord"] != 0:
            raise ValueError("Expected Recognition card")
        fields = {k: v["value"] for k, v in note["fields"].items()}
        expected = {k: v["value"] for k, v in original["fields"].items()}
        if any(
            fields[k] != value for k, value in expected.items() if k not in ("EntryID", "UserNotes")
        ):
            raise ValueError("Legacy note changed after snapshot")
        if fields["EntryID"] not in (expected["EntryID"], entry):
            raise ValueError("Entry identity changed after snapshot")
        found = anki.find_entry(entry)
        if found and found != [nid]:
            raise ValueError("Duplicate stable entry")
        mapped = store.db.execute(
            "SELECT note_id FROM mappings WHERE lemma_key=?", (key,)
        ).fetchone()
        if mapped and mapped[0] != nid:
            raise ValueError("Mapping conflict")
        if fields["EntryID"] != entry:
            anki.call("updateNoteFields", note={"id": nid, "fields": {"EntryID": entry}})
        verified = anki.fields(nid)
        fields["EntryID"] = entry
        if verified != fields:
            raise ValueError("Adoption readback differs")
        cid = digest(["adopt", nid])[:32]
        sid = "adopt-" + str(nid)
        logs = anki.call("getReviewsOfCards", cards=note["cards"])
        first = first_answer(logs.get(str(card["cardId"]), []))
        first_day = (
            study_day(
                datetime.fromtimestamp(first / 1000, timezone.utc), timezone_name, rollover_hour
            )
            if first
            else None
        )
        day = study_day(datetime.now(timezone.utc), timezone_name, rollover_hour)
        payload = {
            "record_kind": "reviewed_legacy_note",
            "lemma": fields["Lemma"],
            "sense_label": spec["sense_label"],
            "context_meaning_zh": fields["PrimaryMeaning"],
        }
        with store.transaction():
            store.db.execute(
                "INSERT OR IGNORE INTO submissions(id,sha,image,state,created) VALUES(?,?,?,'adopted',?)",
                (sid, digest(["adopt", nid]), "", time.time()),
            )
            store.db.execute(
                "INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?,'written',?)",
                (
                    cid,
                    sid,
                    key,
                    sense,
                    key,
                    json.dumps(payload, ensure_ascii=False),
                    0,
                    time.time(),
                ),
            )
            store.db.execute(
                "INSERT OR REPLACE INTO mappings VALUES(?,?,?,?,?)",
                (
                    key,
                    nid,
                    json.dumps(fields, ensure_ascii=False),
                    json.dumps({"Recognition": sense}),
                    time.time(),
                ),
            )
            store.db.execute(
                "INSERT OR IGNORE INTO operations(id,candidate_id,core_key,card_key,is_context,day,state,plan,note_id,card_id,first_day,first_review,created) VALUES(?,?,?,?,0,?,'sync_requested',?,?,?,?,?,?)",
                (
                    cid,
                    cid,
                    key,
                    digest([key, "Recognition"]),
                    day,
                    json.dumps({"kind": "adopt", "note_id": nid}),
                    nid,
                    card["cardId"],
                    first_day,
                    first,
                    time.time(),
                ),
            )
            store.event(
                "legacy_adopted", cid, {"note_id": nid, "card_id": card["cardId"], "scored": False}
            )
