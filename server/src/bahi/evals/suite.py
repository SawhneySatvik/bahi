"""Eval suite schema + loader. Suites are YAML files in server/evals/suites/.

A case seeds a FRESH database via `given`, then runs one or more `turns`
through the real pipeline. Expectations per turn:
- gold_intents: which specialists should handle it ([] = none, e.g. chitchat)
- expected_tools: tool names that MUST be called (subset check; unexpected
  MUTATING tools are a failure — reads are free)
- expected_ledger_delta: canonical multiset of writes; [] = no writes allowed
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

MUTATING_TOOLS = {"add_sale", "add_udhaar", "record_repayment"}


class GivenTransaction(BaseModel):
    type: str  # sale | udhaar | repayment
    amount_paise: int
    customer: str | None = None


class Given(BaseModel):
    transactions: list[GivenTransaction] = Field(default_factory=list)


class ExpectedWrite(BaseModel):
    type: str
    amount_paise: int
    customer: str | None = None  # compared on normalized name


class TurnSpec(BaseModel):
    utterance: str
    gold_intents: list[str] = Field(default_factory=list)
    gold_intent: str | None = None  # sugar for single intent
    # Some queries legitimately route to more than one specialist (balance ->
    # khata OR insights). Any listed intent counts; the sentinel "none" accepts
    # an un-delegated turn (orchestrator answered/clarified itself).
    gold_intents_any: list[str] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    expected_ledger_delta: list[ExpectedWrite] = Field(default_factory=list)
    # --- audio turns (voice pipeline instead of text) ---
    audio: str | None = None  # path relative to server/evals/audio/
    gold_transcript: str | None = None  # WER reference; defaults to utterance
    tts_text: str | None = None  # what audio_synth speaks; defaults to gold/utterance

    @model_validator(mode="after")
    def _merge_intent_sugar(self) -> TurnSpec:
        if (
            self.gold_intent
            and self.gold_intent != "none"
            and self.gold_intent not in self.gold_intents
        ):
            self.gold_intents.append(self.gold_intent)
        return self


class CaseSpec(BaseModel):
    id: str
    lang: str = "hi-en"
    tags: list[str] = Field(default_factory=list)
    given: Given = Field(default_factory=Given)
    turns: list[TurnSpec]


class Suite(BaseModel):
    suite: str
    cases: list[CaseSpec]


def load_suite(path: Path) -> Suite:
    return Suite.model_validate(yaml.safe_load(path.read_text()))


def suite_path(name: str) -> Path:
    return Path(__file__).parents[3] / "evals" / "suites" / f"{name}.yaml"
