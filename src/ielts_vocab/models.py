from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def lemma_key(lemma: str) -> str:
    value = " ".join(unicodedata.normalize("NFKC", lemma).casefold().split())
    if not value or len(value) > 120 or any(c in value for c in '<>\n\r"'):
        raise ValueError("Invalid lemma")
    return "en:" + value


def study_day(at: datetime, timezone: str, rollover_hour: int) -> str:
    if at.tzinfo is None or not 0 <= rollover_hour <= 23:
        raise ValueError("Aware timestamp and rollover hour 0..23 required")
    return (at.astimezone(ZoneInfo(timezone)) - timedelta(hours=rollover_hour)).date().isoformat()


class Evidence(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    kind: Literal["source", "frequency", "cefr", "academic", "dictionary", "history", "inferred"]
    provider: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=1500)
    reference: str = Field(max_length=1000)
    version: str | None


class Candidate(StrictModel):
    surface_form: str = Field(min_length=1, max_length=150)
    lemma: str = Field(min_length=1, max_length=120)
    part_of_speech: str = Field(max_length=50)
    unit_type: Literal["word", "phrase"]
    mark_type: Literal["unknown", "partial", "phrase_context_unclear"]
    source_sentence: str = Field(min_length=1, max_length=2500)
    context_meaning_zh: str = Field(max_length=1200)
    sense_label: str = Field(min_length=1, max_length=200)
    decision: Literal["ACCEPT", "DEFER", "REJECT"]
    reason: str = Field(min_length=1, max_length=1200)
    evidence_refs: list[str] = Field(max_length=30)
    uncertainties: list[str] = Field(max_length=20)
    collocations: list[str] = Field(max_length=2)
    confidence: float = Field(ge=0, le=1)
    gap: float = Field(ge=0, le=100)
    reuse: float = Field(ge=0, le=100)
    academic: float | None = Field(ge=0, le=100)
    context_impact: float = Field(ge=0, le=100)
    difficulty_fit: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def check(self):
        lemma_key(self.lemma)
        if self.decision == "ACCEPT" and (
            not self.context_meaning_zh or not self.evidence_refs or self.uncertainties
        ):
            raise ValueError("ACCEPT needs meaning, evidence, and no unresolved uncertainties")
        return self

    @property
    def priority(self) -> float:
        values = [
            (self.gap, 35),
            (self.reuse, 20),
            (self.academic, 15),
            (self.context_impact, 20),
            (self.difficulty_fit, 10),
        ]
        present = [(v, w) for v, w in values if v is not None]
        return round(sum(v * w for v, w in present) / sum(w for _, w in present), 2)


class Analysis(StrictModel):
    candidates: list[Candidate] = Field(max_length=60)
    notes: str = Field(max_length=2000)


class DayState(StrictModel):
    day: str
    core_limit: int = Field(ge=0, le=35)
    card_limit: int = Field(ge=0, le=35)
    context_limit: int = Field(default=5, ge=0, le=5)
    recovery: bool = True
    reviews_clear: bool = False
    history_verified_at: float = 0
    # A new snapshot must reflect all previously released cards and the study handoff.
    mobile_handoff_confirmed: bool = False
    exceptional_day: bool = False
    history_authority: Literal["manual_handoff", "synced_mac"] = "manual_handoff"
    sync_verified_at: float = 0

    @property
    def handoff_ready(self):
        if self.history_authority == "synced_mac":
            return self.sync_verified_at > 0 and self.history_verified_at >= self.sync_verified_at
        return self.mobile_handoff_confirmed

    @model_validator(mode="after")
    def limits(self):
        if max(self.core_limit, self.card_limit) > 30 and not self.exceptional_day:
            raise ValueError("31..35 requires an explicitly qualified exceptional day")
        if self.recovery and (self.core_limit or self.card_limit):
            raise ValueError("Recovery day must have zero new-word/card limits")
        return self
