from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .models import DayState

DDL = """
CREATE TABLE IF NOT EXISTS submissions(
 id TEXT PRIMARY KEY, sha TEXT NOT NULL, image TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'received', created REAL NOT NULL,
 analysis TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS submissions_sha ON submissions(sha);
CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, sha TEXT NOT NULL, submission TEXT NOT NULL REFERENCES submissions(id));
CREATE TABLE IF NOT EXISTS candidates(
 id TEXT PRIMARY KEY, submission TEXT NOT NULL REFERENCES submissions(id),
 lemma_key TEXT NOT NULL, sense_key TEXT NOT NULL, core_key TEXT NOT NULL,
 payload TEXT NOT NULL, priority REAL NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operations(
 id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL UNIQUE REFERENCES candidates(id),
 core_key TEXT NOT NULL, card_key TEXT NOT NULL UNIQUE, is_context INTEGER NOT NULL,
 day TEXT NOT NULL, state TEXT NOT NULL, plan TEXT NOT NULL, note_id INTEGER,
 card_id INTEGER, first_day TEXT, first_review INTEGER, error TEXT, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS mappings(
 lemma_key TEXT PRIMARY KEY, note_id INTEGER NOT NULL UNIQUE, fields TEXT NOT NULL,
 slots TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(DDL)
        path.chmod(0o600)

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def event(self, kind, ref, detail):
        self.db.execute(
            "INSERT INTO events(at,kind,ref,detail) VALUES(?,?,?,?)",
            (time.time(), kind, ref, json.dumps(detail, ensure_ascii=False)),
        )

    def set_day(self, day: DayState):
        with self.transaction():
            old = self.db.execute("SELECT payload FROM days WHERE day=?", (day.day,)).fetchone()
            if old and DayState.model_validate_json(old[0]).recovery and not day.recovery:
                raise ValueError("Recovery-day latch cannot be lifted on the same day")
            self.db.execute(
                "INSERT OR REPLACE INTO days VALUES(?,?)", (day.day, day.model_dump_json())
            )
            self.event("day_state", day.day, day.model_dump())

    def usage(self, day):
        # Unlearned issued inventory remains reserved across every date boundary.
        rows = self.db.execute("SELECT * FROM operations WHERE state != 'cancelled'").fetchall()
        cores_today = {r["core_key"] for r in rows if r["first_day"] == day}
        learned_before = {r["core_key"] for r in rows if r["first_day"] and r["first_day"] < day}
        reserved = {r["core_key"] for r in rows if not r["first_day"]} - learned_before
        active = [r for r in rows if not r["first_day"] or r["first_day"] == day]
        return {
            "cores": len((cores_today | reserved) - learned_before),
            "cards": len(active),
            "contexts": sum(r["is_context"] for r in active),
        }

    def reserve(self, op_id, candidate_id, core_key, card_key, is_context, day, plan):
        with self.transaction():
            existing = self.db.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone()
            if existing:
                return dict(existing)
            row = self.db.execute("SELECT payload FROM days WHERE day=?", (day,)).fetchone()
            if not row:
                raise ValueError("No verified learning-day budget")
            policy = DayState.model_validate_json(row[0])
            if policy.recovery or not policy.reviews_clear or not policy.mobile_handoff_confirmed:
                raise ValueError("Review-first / sync-handoff gate closed")
            if not 0 <= time.time() - policy.history_verified_at <= 300:
                raise ValueError("History snapshot expired; refresh before admission")
            old_core = self.db.execute(
                "SELECT 1 FROM operations WHERE core_key=? AND state!='cancelled'", (core_key,)
            ).fetchone()
            u = self.usage(day)
            if (
                u["cores"] + (not old_core) > policy.core_limit
                or u["cards"] + 1 > policy.card_limit
                or u["contexts"] + int(is_context) > policy.context_limit
            ):
                raise ValueError("Daily core/card/context budget exhausted")
            self.db.execute(
                "INSERT INTO operations(id,candidate_id,core_key,card_key,is_context,day,"
                "state,plan,created) VALUES(?,?,?,?,?,?,'reserved',?,?)",
                (
                    op_id,
                    candidate_id,
                    core_key,
                    card_key,
                    int(is_context),
                    day,
                    json.dumps(plan, ensure_ascii=False),
                    time.time(),
                ),
            )
            self.db.execute("UPDATE candidates SET state='reserved' WHERE id=?", (candidate_id,))
            self.event("reserved", op_id, {"day": day, "core_key": core_key, "card_key": card_key})
            return dict(self.db.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone())

    def require_write_gate(self, day):
        row = self.db.execute("SELECT payload FROM days WHERE day=?", (day,)).fetchone()
        if not row:
            raise ValueError("No verified learning-day budget")
        policy = DayState.model_validate_json(row[0])
        if policy.recovery or not policy.reviews_clear or not policy.mobile_handoff_confirmed:
            raise ValueError("Review-first / sync-handoff gate closed")
        if not 0 <= time.time() - policy.history_verified_at <= 300:
            raise ValueError("History snapshot expired; refresh before admission")
        used = self.usage(day)
        if (
            used["cores"] > policy.core_limit
            or used["cards"] > policy.card_limit
            or used["contexts"] > policy.context_limit
        ):
            raise ValueError("Existing inventory exceeds today's budget")
        return policy

    def mark_learned(self, op_id, day, review_id):
        with self.transaction():
            row = self.db.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone()
            if not row or not row["card_id"]:
                raise ValueError("Cannot mark an unverified card learned")
            if row["first_review"] and row["first_review"] <= review_id:
                return
            self.db.execute(
                "UPDATE operations SET first_day=?,first_review=? WHERE id=?",
                (day, review_id, op_id),
            )
            self.event("first_review", op_id, {"day": day, "review_id": review_id})

    def mining_paused(self, pending):
        with self.transaction():
            row = self.db.execute("SELECT value FROM settings WHERE key='mining_paused'").fetchone()
            paused = bool(row and row[0] == "true")
            if pending >= 60:
                paused = True
            elif pending < 30:
                paused = False
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES('mining_paused',?)",
                ("true" if paused else "false",),
            )
            return paused

    def status(self):
        return {
            table: [
                dict(r)
                for r in self.db.execute(
                    f"SELECT state,count(*) AS count FROM {table} GROUP BY state"
                )
            ]
            for table in ("submissions", "candidates", "operations")
        }
