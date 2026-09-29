import asyncio
import random

from dadi import report
from dadi.detector import Prediction
from dadi.persona import HANDOFF, Persona
from dadi.session import CallSession, CallStore
from dadi.tactics import TacticBandit


class FakeDetector:
    """Scores a transcript as a scam when it mentions scam keywords."""

    def predict(self, text):
        p = 0.95 if any(w in text for w in ("arrest", "upi", "otp")) else 0.1
        return Prediction(p, "digital_arrest" if p > 0.5 else None, {"digital_arrest": p, "kyc_bank": 1 - p})

    def tactics(self, text):
        return {"fear": 0.9} if "arrest" in text else {}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(tmp_path, monkeypatch):
    monkeypatch.delenv("DADI_LLM_API_KEY", raising=False)
    clock = Clock()
    s = CallSession(FakeDetector(), TacticBandit(tmp_path / "b.json", rng=random.Random(0)),
                    Persona(rng=random.Random(0)), CallStore(tmp_path / "calls.jsonl"), clock=clock)
    return s, clock


def test_scam_call_engages_dadi_and_is_saved_with_intel(tmp_path, monkeypatch):
    s, clock = make(tmp_path, monkeypatch)
    ev = asyncio.run(s.on_caller("main CBI se, aapka arrest warrant hai"))
    assert ev["state"] == "engaged" and ev["move"] is not None
    clock.t = 90
    ev = asyncio.run(s.on_caller("paise bhejo cbi dot safe at the rate paytm"))
    assert ev["new_intel"]["upi_ids"] == ["cbi.safe@paytm"]
    clock.t = 400
    record = s.end()
    assert record["wasted_s"] == 400
    assert record["intel"]["upi_ids"] == ["cbi.safe@paytm"]
    assert s.store.get(s.id)["scam_type"] == "digital_arrest"
    # Dadi's first move earned a success plus an intel bonus; the last one a loss.
    total = sum(a.wins + a.losses for a in s.bandit.arms["_global"].values())
    assert total == 3
    assert "cbi.safe@paytm" in report.draft(record)


def test_genuine_call_is_handed_back_and_not_saved(tmp_path, monkeypatch):
    s, _ = make(tmp_path, monkeypatch)
    asyncio.run(s.on_caller("hello mummy main Rohit bol raha hoon"))
    ev = asyncio.run(s.on_caller("khana kha liya aapne"))
    assert ev["state"] == "handoff" and ev["text"] == HANDOFF
    assert s.end() is None
    assert s.store.all() == []
