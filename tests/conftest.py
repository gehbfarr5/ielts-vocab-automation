import io
import time

import pytest
from PIL import Image

from ielts_vocab.ingest import receive
from ielts_vocab.models import Candidate, DayState, digest, lemma_key
from ielts_vocab.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "state.sqlite3")
    yield s
    s.db.close()


@pytest.fixture
def image_bytes():
    out = io.BytesIO()
    Image.new("RGB", (300, 100), "white").save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def candidate():
    return Candidate(
        surface_form="maintain",
        lemma="maintain",
        part_of_speech="verb",
        unit_type="word",
        mark_type="partial",
        source_sentence="We maintain the system.",
        context_meaning_zh="维护",
        sense_label="keep in good condition",
        decision="ACCEPT",
        reason="Reusable vocabulary in the current context",
        evidence_refs=["source:test"],
        uncertainties=[],
        collocations=["maintain a system"],
        confidence=0.99,
        gap=80,
        reuse=90,
        academic=None,
        context_impact=80,
        difficulty_fit=85,
    )


def put_candidate(store, tmp_path, image_bytes, c, suffix=""):
    receipt = receive(store, tmp_path, image_bytes)
    key = lemma_key(c.lemma)
    sense = digest([key, c.part_of_speech.casefold(), c.sense_label.casefold()])[:24]
    cid = digest([key, sense, suffix])[:32]
    store.db.execute(
        "INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?)",
        (
            cid,
            receipt["submission_id"],
            key,
            sense,
            key,
            c.model_dump_json(),
            c.priority,
            "pending",
            time.time(),
        ),
    )
    return dict(store.db.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone())


def open_day(store, day="2026-09-16", limit=20, card_limit=30):
    store.set_day(
        DayState(
            day=day,
            core_limit=limit,
            card_limit=card_limit,
            recovery=False,
            reviews_clear=True,
            mobile_handoff_confirmed=True,
            history_verified_at=time.time(),
            exceptional_day=limit > 30 or card_limit > 30,
        )
    )
