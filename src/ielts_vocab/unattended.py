"""Admission based on observable synced collection state, never invented mobile state."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .anki import reconcile_completed_writes, reconcile_reviews
from .models import DayState, study_day


def refresh_day(store, anki, config):
    if config.get("history_authority") != "synced_mac":
        raise ValueError("Synced-history policy not selected")
    limit = config.get("daily_new_limit", 25)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 30:
        raise ValueError("Unattended daily limit must be 0..30; exceptional days remain explicit")
    day = study_day(datetime.now(timezone.utc), config["timezone"], config["rollover_hour"])
    old = store.db.execute("SELECT payload FROM days WHERE day=?", (day,)).fetchone()
    if old and DayState.model_validate_json(old[0]).recovery:
        return {"state": "waiting_recovery_day"}
    previous = store.db.execute(
        "SELECT value FROM settings WHERE key='last_admission_sync'"
    ).fetchone()
    interval = config.get("admission_sync_interval_seconds", 300)
    if not isinstance(interval, int) or interval < 60:
        raise ValueError("Admission sync interval must be at least 60 seconds")
    if previous and 0 <= time.time() - float(previous[0]) < interval:
        return {"state": "waiting_sync_interval"}
    # No cached success may authorize writes after a failed sync.
    anki.call("sync")
    reconcile_completed_writes(store, anki)
    store.db.execute("UPDATE operations SET state='sync_requested' WHERE state='written'")
    store.db.execute("DELETE FROM settings WHERE key='sync_dirty'")
    synced_at = time.time()
    store.db.execute(
        "INSERT OR REPLACE INTO settings VALUES('last_admission_sync',?)", (str(synced_at),)
    )
    deck = config["anki_deck"]
    if any(char in deck for char in '\\"\n\r'):
        raise ValueError("Deck cannot be safely represented in a search")
    cards = set(anki.call("findCards", query=f'deck:"{deck}"'))
    tracked = {
        r[0] for r in store.db.execute("SELECT card_id FROM operations WHERE card_id IS NOT NULL")
    }
    if cards != tracked:
        raise ValueError(
            "Deck inventory differs from ledger; reconcile before unattended admission"
        )
    reconcile_reviews(store, anki, config["timezone"], config["rollover_hour"])
    due = anki.call("findCards", query="is:due")
    history_rows = []
    for mapped in store.db.execute("SELECT lemma_key,note_id FROM mappings"):
        note = anki.note(mapped["note_id"])
        details = anki.call("cardsInfo", cards=note["cards"])
        reviews = anki.call("getReviewsOfCards", cards=note["cards"])
        history_rows.append(
            {
                "lemma": mapped["lemma_key"].removeprefix("en:"),
                "cards": [
                    {
                        "card_id": c["cardId"],
                        "interval": c["interval"],
                        "reps": c["reps"],
                        "lapses": c["lapses"],
                    }
                    for c in details
                ],
                "recent_reviews": {
                    k: sorted(v, key=lambda x: x["id"])[-10:] for k, v in reviews.items()
                },
            }
        )
    store.db.execute(
        "INSERT OR REPLACE INTO settings VALUES('synced_history',?)",
        (json.dumps({"observed_at": time.time(), "entries": history_rows}),),
    )
    policy = DayState(
        day=day,
        core_limit=limit,
        card_limit=limit,
        context_limit=min(5, limit),
        recovery=False,
        reviews_clear=not due,
        history_authority="synced_mac",
        sync_verified_at=synced_at,
        history_verified_at=time.time(),
        mobile_handoff_confirmed=False,
    )
    store.set_day(policy)
    usage = store.usage(day)
    store.event(
        "synced_history_observed",
        day,
        {
            "due_count": len(due),
            "usage": usage,
            "sync_verified_at": synced_at,
            "mobile_offline_state_known": False,
        },
    )
    if due:
        return {"state": "waiting_reviews", "due_count": len(due)}
    unresolved = store.db.execute(
        "SELECT 1 FROM operations WHERE state IN ('reserved','writing','write_uncertain')"
    ).fetchone()
    if (
        usage["cores"] > limit
        or usage["cards"] > limit
        or (not unresolved and (usage["cores"] >= limit or usage["cards"] >= limit))
    ):
        return {"state": "waiting_budget", "usage": usage}
    return {"state": "ready", "day": day, "usage": usage}
