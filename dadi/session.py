"""One phone call: screening → Dadi engaged (scam) or handed back (legit) → ended."""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from dadi.detector import Detector
from dadi.extract import Intel, extract
from dadi.persona import HANDOFF, Persona
from dadi.tactics import TacticBandit

ENGAGE_AT = 0.8     # scam probability at which Dadi takes over
HANDOFF_BELOW = 0.3  # after MIN_SCREEN_TURNS, calls this clean go back to the user
MIN_SCREEN_TURNS = 2


class CallStore:
    def __init__(self, path: Path):
        self.path = path

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def get(self, call_id: str) -> dict | None:
        return next((r for r in self.all() if r["id"] == call_id), None)

    def add(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class CallSession:
    def __init__(self, detector: Detector, bandit: TacticBandit, persona: Persona, store: CallStore,
                 clock=time.monotonic):
        self.id = "C" + uuid.uuid4().hex[:6].upper()
        self.detector, self.bandit, self.persona, self.store = detector, bandit, persona, store
        self.clock = clock
        self.state = "screening"
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.t0 = clock()
        self.engaged_at: float | None = None
        self.history: list[dict] = []
        self.intel = Intel()
        self.tactics_seen: Counter[str] = Counter()
        self.moves: Counter[str] = Counter()
        self.scam_prob = 0.0
        self.scam_type: str | None = None
        self.type_probs: dict[str, float] = {}
        self.pending_move: str | None = None
        self.last_move: str | None = None

    @property
    def wasted_s(self) -> int:
        return int(self.clock() - self.engaged_at) if self.engaged_at is not None else 0

    def _caller_text(self) -> str:
        return " ".join(h["text"] for h in self.history if h["role"] == "caller")

    async def on_caller(self, text: str) -> dict:
        text = text.strip()
        self.history.append({"role": "caller", "text": text, "t": round(self.clock() - self.t0, 1)})
        new_intel = self.intel.merge(extract(text))
        utter_tactics = self.detector.tactics(text)
        self.tactics_seen.update(utter_tactics.keys())

        # The scammer answered Dadi's previous move: that move kept them talking.
        if self.pending_move:
            self.bandit.update(self.scam_type, self.pending_move, continued=True, new_intel=not new_intel.is_empty())
            self.pending_move = None

        pred = self.detector.predict(self._caller_text())
        self.scam_prob, self.type_probs = pred.scam_prob, pred.type_probs
        if pred.scam_type:
            self.scam_type = pred.scam_type
        caller_turns = sum(h["role"] == "caller" for h in self.history)

        move, source = None, "scripted"
        if self.state == "screening":
            if self.scam_prob >= ENGAGE_AT:
                self.state, self.engaged_at = "engaged", self.clock()
            elif caller_turns >= MIN_SCREEN_TURNS and self.scam_prob < HANDOFF_BELOW:
                self.state = "handoff"

        if self.state == "engaged":
            move = self.bandit.choose(self.scam_type, exclude=self.last_move)
            line, source = await self.persona.reply(move, self.history, self.scam_type)
            self.pending_move = self.last_move = move
            self.moves[move] += 1
        elif self.state == "handoff":
            line = HANDOFF
        elif caller_turns == 1:
            line = self.persona.screening_line()
        else:
            # Still unsure: stall politely without committing to the act.
            line = self.persona.fallback("bad_connection" if caller_turns % 2 else "ask_details", text)

        self.history.append({"role": "dadi", "text": line, "t": round(self.clock() - self.t0, 1), "move": move})
        return {
            "type": "dadi",
            "text": line,
            "move": move,
            "source": source,
            "state": self.state,
            "utterance_tactics": utter_tactics,
            "new_intel": new_intel.to_dict(),
            **self.snapshot(),
        }

    def snapshot(self) -> dict:
        return {
            "call_id": self.id,
            "state": self.state,
            "scam_prob": round(self.scam_prob, 3),
            "scam_type": self.scam_type,
            "type_probs": {k: round(v, 3) for k, v in sorted(self.type_probs.items(), key=lambda kv: -kv[1])},
            "tactics_seen": dict(self.tactics_seen),
            "intel": self.intel.to_dict(),
            "wasted_s": self.wasted_s,
            "bandit": self.bandit.stats(self.scam_type),
        }

    def end(self) -> dict | None:
        """Caller hung up. Scores Dadi's last move as a loss and saves scam calls."""
        if self.pending_move:
            self.bandit.update(self.scam_type, self.pending_move, continued=False)
            self.pending_move = None
        was_engaged = self.state == "engaged"
        wasted = self.wasted_s
        self.state = "ended"
        if not was_engaged:
            return None
        record = {
            "id": self.id,
            "started_at": self.started_at,
            "scam_type": self.scam_type,
            "scam_prob": round(self.scam_prob, 3),
            "wasted_s": wasted,
            "tactics": [t for t, _ in self.tactics_seen.most_common()],
            "dadi_moves": dict(self.moves),
            "intel": self.intel.to_dict(),
            "transcript": self.history,
        }
        self.store.add(record)
        return record
