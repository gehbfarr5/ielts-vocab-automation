import concurrent.futures
import time
from datetime import datetime, timezone

import pytest
from conftest import open_day, put_candidate

from ielts_vocab.models import DayState, study_day
from ielts_vocab.store import Store


def test_day_rollover_and_aware_time():
    assert (
        study_day(datetime(2026, 9, 16, 19, tzinfo=timezone.utc), "Asia/Shanghai", 4)
        == "2026-09-16"
    )
    assert (
        study_day(datetime(2026, 9, 16, 20, tzinfo=timezone.utc), "Asia/Shanghai", 4)
        == "2026-09-17"
    )
    with pytest.raises(ValueError):
        study_day(datetime(2026, 9, 16), "Asia/Shanghai", 4)


def test_reserved_inventory_survives_midnight(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    open_day(store, limit=1)
    store.reserve("op1", c["id"], c["core_key"], "card1", False, "2026-09-16", {})
    assert store.usage("2026-09-17") == {"cores": 1, "cards": 1, "contexts": 0}
    open_day(store, day="2026-09-17", limit=1)
    c2 = put_candidate(
        store, tmp_path, image_bytes, candidate.model_copy(update={"lemma": "other"})
    )
    with pytest.raises(ValueError, match="exhausted"):
        store.reserve("op2", c2["id"], c2["core_key"], "card2", False, "2026-09-17", {})


def test_context_consumes_card_budget_not_new_core(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    open_day(store, limit=1, card_limit=1)
    store.reserve("op1", c["id"], c["core_key"], "card1", False, "2026-09-16", {})
    c2 = put_candidate(store, tmp_path, image_bytes, candidate, suffix="second")
    with pytest.raises(ValueError, match="exhausted"):
        store.reserve("op2", c2["id"], c["core_key"], "card2", True, "2026-09-16", {})


def test_actual_answer_replaces_reservation(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    open_day(store)
    store.reserve("op", c["id"], c["core_key"], "card", False, "2026-09-16", {})
    store.db.execute("UPDATE operations SET card_id=123 WHERE id='op'")
    store.mark_learned("op", "2026-09-16", 12345)
    store.mark_learned("op", "2026-09-17", 23456)
    assert store.usage("2026-09-16")["cores"] == 1
    assert store.usage("2026-09-17")["cores"] == 0
    assert store.db.execute("SELECT first_review FROM operations").fetchone()[0] == 12345


def test_recovery_latches_for_whole_day(store):
    store.set_day(DayState(day="2026-09-16", core_limit=0, card_limit=0))
    with pytest.raises(ValueError, match="latch"):
        open_day(store)
    open_day(store, day="2026-09-17")


def test_stale_history_blocks(store, tmp_path, image_bytes, candidate):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    store.set_day(
        DayState(
            day="2026-09-16",
            core_limit=20,
            card_limit=30,
            recovery=False,
            reviews_clear=True,
            mobile_handoff_confirmed=True,
            history_verified_at=time.time() - 301,
        )
    )
    with pytest.raises(ValueError, match="expired"):
        store.reserve("op", c["id"], c["core_key"], "card", False, "2026-09-16", {})


def test_last_slot_concurrent_reservations(store, tmp_path, image_bytes, candidate):
    c1 = put_candidate(store, tmp_path, image_bytes, candidate)
    c2 = put_candidate(
        store, tmp_path, image_bytes, candidate.model_copy(update={"lemma": "other"})
    )
    open_day(store, limit=1)

    def attempt(c):
        own = Store(tmp_path / "state.sqlite3")
        try:
            own.reserve(c["id"], c["id"], c["core_key"], c["id"], False, "2026-09-16", {})
            return True
        except ValueError:
            return False
        finally:
            own.db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt, [c1, c2])) == 1
    assert store.usage("2026-09-16")["cores"] == 1


def test_exceptional_day_required():
    with pytest.raises(ValueError, match="exceptional"):
        DayState(day="2026-09-16", core_limit=35, card_limit=35, recovery=False)


def test_uncertain_unwritten_operation_cannot_cross_into_recovery(
    store, tmp_path, image_bytes, candidate
):
    from test_anki import FakeAnki

    from ielts_vocab.anki import execute, make_plan

    c = put_candidate(store, tmp_path, image_bytes, candidate)
    a = FakeAnki()
    open_day(store)
    p = make_plan(store, a, c, "IELTS")
    store.reserve("op", c["id"], c["core_key"], "card", False, "2026-09-16", p)
    store.set_day(DayState(day="2026-09-17", core_limit=0, card_limit=0))
    with pytest.raises(ValueError, match="gate closed"):
        execute(store, a, "op", current_day="2026-09-17")
    assert a.adds == 0


def test_mining_backpressure_requires_drain_below_thirty(store):
    assert not store.mining_paused(50)
    assert store.mining_paused(60)
    assert store.mining_paused(45)
    assert store.mining_paused(30)
    assert not store.mining_paused(29)
