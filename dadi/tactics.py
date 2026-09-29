"""Which stalling move should Dadi use next?

A contextual Thompson-sampling bandit. Arms are stalling tactics; context is
the detected scam type (a "digital arrest" caller may tolerate different
nonsense than a "KYC" caller). Each (context, tactic) keeps a Beta posterior
over "the scammer kept talking after this move". Moves that also got the
scammer to reveal a new identifier earn an extra success, so Dadi learns to
waste time *and* harvest intel.

Context-specific posteriors start from the global posterior (shrinkage), so a
brand-new scam type still benefits from everything learned so far.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

TACTICS = {
    "mishear": "Deliberately mishear a key word the scammer just said and ask about the wrong thing.",
    "hold_on": "Ask them to hold while you look for your glasses, pen, diary or the right phone.",
    "long_story": "Drift into a long, loving story (grandson's wedding, knee pain, TV serial, neighbour's dog).",
    "tech_confusion": "Get confused by the technology they mention (UPI, app, OTP, link) and ask them to explain slowly.",
    "fake_compliance": "Sound eager to comply but do it wrong: read out wrong digits slowly, open the wrong app, go to the wrong bank.",
    "ask_details": "Innocently ask them to repeat their full name, badge number, UPI ID, account number or phone number 'so I can write it down'.",
    "bad_connection": "Pretend the line is breaking up and ask them to repeat everything louder.",
}
PRIOR = (1.0, 1.0)
SHRINK = 0.3  # weight of the global posterior folded into a context's prior


@dataclass
class Arm:
    wins: float = 0.0
    losses: float = 0.0


class TacticBandit:
    def __init__(self, path: Path | None = None, rng: random.Random | None = None):
        self.path = path
        self.rng = rng or random.Random()
        self.arms: dict[str, dict[str, Arm]] = {"_global": {t: Arm() for t in TACTICS}}
        if path and path.exists():
            raw = json.loads(path.read_text())
            for ctx, arms in raw.items():
                self.arms[ctx] = {t: Arm(**a) for t, a in arms.items() if t in TACTICS}
                for t in TACTICS:
                    self.arms[ctx].setdefault(t, Arm())

    def _posterior(self, context: str, tactic: str) -> tuple[float, float]:
        g = self.arms["_global"][tactic]
        if context == "_global":
            return PRIOR[0] + g.wins, PRIOR[1] + g.losses
        c = self.arms.get(context, {}).get(tactic, Arm())
        return PRIOR[0] + c.wins + SHRINK * g.wins, PRIOR[1] + c.losses + SHRINK * g.losses

    def choose(self, context: str | None, exclude: str | None = None) -> str:
        """Sample a tactic; `exclude` avoids repeating the previous move."""
        ctx = context or "_global"
        samples = {t: self.rng.betavariate(*self._posterior(ctx, t)) for t in TACTICS if t != exclude}
        return max(samples, key=samples.get)

    def update(self, context: str | None, tactic: str, continued: bool, new_intel: bool = False) -> None:
        for ctx in {context or "_global", "_global"}:
            arm = self.arms.setdefault(ctx, {t: Arm() for t in TACTICS})[tactic]
            if continued:
                arm.wins += 1
            else:
                arm.losses += 1
            if new_intel:
                arm.wins += 1
        self.save()

    def stats(self, context: str | None = None) -> dict[str, dict[str, float]]:
        ctx = context or "_global"
        out = {}
        for t in TACTICS:
            a, b = self._posterior(ctx, t)
            out[t] = {"mean": round(a / (a + b), 3), "n": round(a + b - 2, 1)}
        return out

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {ctx: {t: vars(a) for t, a in arms.items()} for ctx, arms in self.arms.items()}
        self.path.write_text(json.dumps(data, indent=1))
