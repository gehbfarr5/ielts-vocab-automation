from __future__ import annotations

import html
import json
import time
import urllib.request
from datetime import datetime, timezone

from .card_layout import BACK, CSS, FRONT
from .models import Candidate, digest, study_day
from .store import Store

MODEL = "IELTS Lexeme v1"
FIELDS = [
    "EntryID",
    "Lemma",
    "CoreCountKey",
    "RecognitionPrompt",
    "PrimaryMeaning",
    "PrimarySentence",
    "Collocations",
    "Context1Prompt",
    "Context1Answer",
    "Context1SenseID",
    "Context2Prompt",
    "Context2Answer",
    "Context2SenseID",
    "Sources",
    "UserNotes",
    "PronunciationText",
    "IPA_US",
    "IPA_UK",
    "IPA_Note",
    "IPA_Source",
]
TEMPLATES = [
    {
        "Name": "Recognition",
        "Front": FRONT,
        "Back": BACK,
    },
    *[
        {
            "Name": f"Context {i}",
            "Front": f"{{{{#Context{i}Answer}}}}{{{{#Context{i}Prompt}}}}{{{{Context{i}Prompt}}}}"
            f"{{{{/Context{i}Prompt}}}}{{{{/Context{i}Answer}}}}",
            "Back": f'{{{{FrontSide}}}}<hr id="answer">{{{{Context{i}Answer}}}}',
        }
        for i in (1, 2)
    ],
]


class AnkiError(RuntimeError):
    pass


class Anki:
    def __init__(self, profile: str, key: str | None = None, url="http://127.0.0.1:8765"):
        if url != "http://127.0.0.1:8765":
            raise ValueError("Anki control endpoint must remain on loopback")
        self.profile, self.key, self.url = profile, key, url

    def call(self, action, **params):
        body = {"action": action, "version": 6, "params": params}
        if self.key:
            body["key"] = self.key
        req = urllib.request.Request(
            self.url, json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.load(response)
        if set(payload) != {"result", "error"} or payload["error"]:
            raise AnkiError(f"{action}: {payload.get('error', 'invalid response')}")
        return payload["result"]

    def guard(self):
        actual = self.call("getActiveProfile")
        if actual != self.profile:
            raise AnkiError("Active profile differs from configured profile")

    def setup(self, deck):
        self.guard()
        if MODEL not in self.call("modelNames"):
            self.call(
                "createModel",
                modelName=MODEL,
                inOrderFields=FIELDS,
                css=CSS,
                isCloze=False,
                cardTemplates=TEMPLATES,
            )
        if self.call("modelFieldNames", modelName=MODEL) != FIELDS:
            raise AnkiError("Managed model schema mismatch; no automatic migration")
        actual = self.call("modelTemplates", modelName=MODEL)
        expected = {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in TEMPLATES}
        if actual != expected:
            raise AnkiError("Managed templates differ; review before writing")
        self.call("createDeck", deck=deck)

    def note(self, note_id):
        self.guard()
        notes = self.call("notesInfo", notes=[note_id])
        if len(notes) != 1 or notes[0].get("noteId") != note_id:
            raise AnkiError("Mapped note missing")
        return notes[0]

    def fields(self, note_id):
        n = self.note(note_id)
        if n["modelName"] != MODEL:
            raise AnkiError("Mapped note has different model")
        return {k: v["value"] for k, v in n["fields"].items()}

    def find_entry(self, entry):
        self.guard()
        # entry is generated hex, never model/user query text.
        if len(entry) != 32 or any(c not in "0123456789abcdef" for c in entry):
            raise ValueError("Invalid stable EntryID")
        return self.call("findNotes", query=f'note:"{MODEL}" EntryID:{entry}')

    def history(self, query):
        self.guard()
        ids = self.call("findCards", query=query)
        cards, reviews = [], {}
        for offset in range(0, len(ids), 200):
            part = ids[offset : offset + 200]
            cards.extend(self.call("cardsInfo", cards=part))
            reviews.update(self.call("getReviewsOfCards", cards=part))
        return {"cards": cards, "reviews": reviews, "read_at": time.time()}


def first_answer(reviews):
    valid = [r for r in reviews if r.get("ease") in (1, 2, 3, 4) and r.get("type") in (0, 1, 2, 3)]
    return min((r["id"] for r in valid), default=None)


def reconcile_reviews(store, anki, timezone_name, rollover_hour):
    rows = store.db.execute(
        "SELECT id,card_id FROM operations WHERE card_id IS NOT NULL"
    ).fetchall()
    for row in rows:
        logs = anki.call("getReviewsOfCards", cards=[row["card_id"]])
        first = first_answer(logs.get(str(row["card_id"]), []))
        if first:
            day = study_day(
                datetime.fromtimestamp(first / 1000, timezone.utc), timezone_name, rollover_hour
            )
            store.mark_learned(row["id"], day, first)


def render(candidate: Candidate):
    return {
        "RecognitionPrompt": html.escape(candidate.lemma),
        "PronunciationText": html.escape(candidate.lemma),
        "PrimaryMeaning": html.escape(candidate.context_meaning_zh),
        "PrimarySentence": html.escape(candidate.source_sentence),
        "Collocations": "<br>".join(map(html.escape, candidate.collocations)),
    }


def make_plan(store: Store, anki: Anki, candidate_row, deck: str):
    c = Candidate.model_validate_json(candidate_row["payload"])
    key, sense = candidate_row["lemma_key"], candidate_row["sense_key"]
    entry = digest(key)[:32]
    mapping = store.db.execute("SELECT * FROM mappings WHERE lemma_key=?", (key,)).fetchone()
    existing = anki.find_entry(entry)
    if len(existing) > 1:
        raise AnkiError("Duplicate EntryID requires manual reconciliation")
    if not mapping and existing:
        raise AnkiError("Unmapped existing note: recover interrupted operation first")
    if not mapping:
        # Only creation in a scope with explicitly reviewed legacy inventory is allowed.
        fields = dict.fromkeys(FIELDS, "")
        fields.update({"EntryID": entry, "Lemma": html.escape(c.lemma), "CoreCountKey": key})
        fields.update(render(c))
        fields["Sources"] = html.escape(candidate_row["submission"])
        return {
            "kind": "create",
            "entry": entry,
            "lemma_key": key,
            "deck": deck,
            "before": None,
            "fields": fields,
            "slot": "Recognition",
            "sense": sense,
            "slots": {"Recognition": sense},
            "note_id": None,
        }
    if existing != [mapping["note_id"]]:
        raise AnkiError("Entry mapping has changed")
    before = anki.fields(mapping["note_id"])
    saved = json.loads(mapping["fields"])
    # UserNotes is explicitly user-owned; every other manual change must be resolved.
    if any(before.get(k) != v for k, v in saved.items() if k != "UserNotes"):
        raise AnkiError("Managed fields were edited outside the pipeline")
    slots = json.loads(mapping["slots"])
    fields = dict(before)
    if sense in slots.values():
        slot = next(k for k, v in slots.items() if v == sense)
        fields["Sources"] = "<br>".join(
            dict.fromkeys(
                before["Sources"].split("<br>") + [html.escape(candidate_row["submission"])]
            )
        )
        kind = "enrich"
    else:
        slot = next((f"Context {i}" for i in (1, 2) if f"Context {i}" not in slots), None)
        if not slot:
            raise AnkiError("Context capacity full; never reuse a learned sense slot")
        i = slot[-1]
        fields[f"Context{i}Prompt"] = (
            html.escape(c.source_sentence) + "<br>What does the highlighted expression mean?"
        )
        fields[f"Context{i}Prompt"] += "<br><b>" + html.escape(c.surface_form) + "</b>"
        fields[f"Context{i}Answer"] = html.escape(c.context_meaning_zh)
        fields[f"Context{i}SenseID"] = sense
        slots[slot] = sense
        kind = "context"
    return {
        "kind": kind,
        "entry": entry,
        "lemma_key": key,
        "deck": deck,
        "before": before,
        "fields": fields,
        "slot": slot,
        "sense": sense,
        "slots": slots,
        "note_id": mapping["note_id"],
    }


def execute(store, anki, op_id, current_day=None):
    row = store.db.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone()
    if not row:
        raise ValueError("Unknown operation")
    p = json.loads(row["plan"])
    anki.guard()
    try:
        found = anki.find_entry(p["entry"])
        if len(found) > 1:
            raise AnkiError("Duplicate note after interrupted operation")
        store.db.execute("UPDATE operations SET state='writing',error=NULL WHERE id=?", (op_id,))
        if p["kind"] == "create" and not found:
            store.require_write_gate(current_day or row["day"])
            nid = anki.call(
                "addNote",
                note={
                    "deckName": p["deck"],
                    "modelName": MODEL,
                    "fields": p["fields"],
                    "tags": ["ielts_vocab::managed"],
                    "options": {"allowDuplicate": False},
                },
            )
        else:
            nid = found[0] if found else None
            if nid is None or (p["note_id"] and p["note_id"] != nid):
                raise AnkiError("Note vanished or mapping changed")
            actual = anki.fields(nid)
            desired = {k: v for k, v in p["fields"].items() if k != "UserNotes"}
            if any(actual.get(k) != v for k, v in desired.items()):
                if p["before"] is None or any(
                    actual.get(k) != v for k, v in p["before"].items() if k != "UserNotes"
                ):
                    raise AnkiError("Concurrent edit or uncertain write differs from snapshot")
                store.require_write_gate(current_day or row["day"])
                patch = {k: v for k, v in desired.items() if actual[k] != v}
                anki.call("updateNoteFields", note={"id": nid, "fields": patch})
        verified = anki.fields(nid)
        if any(verified.get(k) != v for k, v in p["fields"].items() if k != "UserNotes"):
            raise AnkiError("Anki readback mismatch")
        n = anki.note(nid)
        cards = anki.call("cardsInfo", cards=n["cards"])
        index = {"Recognition": 0, "Context 1": 1, "Context 2": 2}[p["slot"]]
        match = [c for c in cards if c["ord"] == index]
        if len(match) != 1 or len(cards) != len(p["slots"]):
            raise AnkiError("Unexpected generated card count or slot")
        with store.transaction():
            store.db.execute(
                "INSERT OR REPLACE INTO mappings VALUES(?,?,?,?,?)",
                (
                    p["lemma_key"],
                    nid,
                    json.dumps(verified, ensure_ascii=False),
                    json.dumps(p["slots"]),
                    time.time(),
                ),
            )
            store.db.execute(
                "UPDATE operations SET state='written',note_id=?,card_id=? WHERE id=?",
                (nid, match[0]["cardId"], op_id),
            )
            store.db.execute(
                "UPDATE candidates SET state='written' WHERE id=?", (row["candidate_id"],)
            )
            store.event("write_verified", op_id, {"note_id": nid, "card_id": match[0]["cardId"]})
    except Exception as e:
        store.db.execute(
            "UPDATE operations SET state='write_uncertain',error=? WHERE id=?", (str(e), op_id)
        )
        store.event("write_error", op_id, {"type": type(e).__name__})
        raise


def enrich(store, anki, candidate_row, plan):
    # No new card: still snapshot, compare, patch, read back, never count as first learning.
    nid = plan["note_id"]
    before = anki.fields(nid)
    if before != plan["before"]:
        raise AnkiError("Concurrent edit before enrichment")
    store.event("enrich_intent", candidate_row["id"], plan)
    patch = {k: v for k, v in plan["fields"].items() if v != before[k] and k != "UserNotes"}
    if patch:
        anki.call("updateNoteFields", note={"id": nid, "fields": patch})
    after = anki.fields(nid)
    if any(after[k] != v for k, v in plan["fields"].items() if k != "UserNotes"):
        raise AnkiError("Enrichment readback failed")
    with store.transaction():
        store.db.execute(
            "UPDATE mappings SET fields=?,updated=? WHERE note_id=?",
            (json.dumps(after, ensure_ascii=False), time.time(), nid),
        )
        store.db.execute(
            "UPDATE candidates SET state='enriched' WHERE id=?", (candidate_row["id"],)
        )
        store.event("enriched", candidate_row["id"], {"note_id": nid})
