import json
import time
from datetime import datetime, timezone

import pytest
from conftest import put_candidate

from ielts_vocab.models import DayState, study_day
from ielts_vocab.runtime import read_config, require_writer
from ielts_vocab.unattended import refresh_day


class Remote:
    def __init__(self, *, due=None, cards=None, fail=False):
        self.due, self.cards, self.fail = due or [], cards or [], fail
        self.syncs = 0

    def find_entry(self, entry):
        return []

    def call(self, action, **kwargs):
        if action == "sync":
            self.syncs += 1
            if self.fail:
                raise RuntimeError("offline")
        elif action == "findCards":
            return self.due if kwargs["query"] == "is:due" else self.cards
        elif action == "getReviewsOfCards":
            return {}
        else:
            raise AssertionError(action)


@pytest.fixture
def config():
    return dict(
        history_authority="synced_mac",
        daily_new_limit=25,
        timezone="Asia/Shanghai",
        rollover_hour=4,
        anki_deck="IELTS",
    )


def test_ready_without_claiming_mobile_confirmation(store, config):
    assert refresh_day(store, Remote(), config)["state"] == "ready"
    d = DayState.model_validate_json(store.db.execute("SELECT payload FROM days").fetchone()[0])
    assert d.handoff_ready and not d.mobile_handoff_confirmed


def test_failed_sync_never_creates_budget(store, config):
    with pytest.raises(RuntimeError, match="offline"):
        refresh_day(store, Remote(fail=True), config)
    assert not store.db.execute("SELECT * FROM days").fetchall()


def test_due_reviews_wait_without_recovery_latch(store, config):
    r = Remote(due=[1])
    assert refresh_day(store, r, config)["state"] == "waiting_reviews"
    store.db.execute("DELETE FROM settings WHERE key='last_admission_sync'")
    r.due = []
    assert refresh_day(store, r, config)["state"] == "ready"


def test_inventory_mismatch_blocks_new_budget(store, config):
    with pytest.raises(ValueError, match="inventory"):
        refresh_day(store, Remote(cards=[1]), config)
    assert not store.db.execute("SELECT * FROM days").fetchall()


def test_sync_is_throttled(store, config):
    r = Remote()
    refresh_day(store, r, config)
    assert refresh_day(store, r, config)["state"] == "waiting_sync_interval"
    assert r.syncs == 1


def test_reservations_are_charged_before_new_admission(
    store, config, tmp_path, image_bytes, candidate
):
    c = put_candidate(store, tmp_path, image_bytes, candidate)
    config["daily_new_limit"] = 1
    result = refresh_day(store, Remote(), config)
    store.reserve("op", c["id"], c["core_key"], "card", False, result["day"], {"entry": "test"})
    store.db.execute("DELETE FROM settings WHERE key='last_admission_sync'")
    assert refresh_day(store, Remote(), config)["state"] == "ready"
    # Existing reservation may complete; it cannot admit a second card.
    with pytest.raises(ValueError, match="exhausted"):
        store.reserve("another", c["id"], c["core_key"], "another", False, result["day"], {})


def test_recovery_is_not_reopened_by_automation(store, config):
    day = study_day(datetime.now(timezone.utc), "Asia/Shanghai", 4)
    store.set_day(DayState(day=day, core_limit=0, card_limit=0))
    r = Remote()
    assert refresh_day(store, r, config)["state"] == "waiting_recovery_day"
    assert r.syncs == 0


def test_copied_config_cannot_authorize_another_host(monkeypatch):
    monkeypatch.setattr("ielts_vocab.runtime.host_id", lambda: "server")
    with pytest.raises(ValueError, match="handoff"):
        require_writer({"writer_host_id": "laptop"})
    require_writer({"writer_host_id": "server"})


def test_runtime_relative_paths_are_relocated(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"anki_key_file": "production.token", "inbox": "inbox"})
    )
    c = read_config(tmp_path)
    assert c["anki_key_file"] == str(tmp_path / "production.token")
    assert c["inbox"] == str(tmp_path / "inbox")


def test_missing_sync_time_never_authorizes_synced_policy():
    d = DayState(
        day="2026-09-16",
        core_limit=25,
        card_limit=25,
        recovery=False,
        history_authority="synced_mac",
        mobile_handoff_confirmed=True,
        history_verified_at=time.time(),
    )
    assert not d.handoff_ready
