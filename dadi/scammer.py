"""Simulated scammer for the "Watch a demo call" mode.

Lets judges (and the demo video) see a full call without anyone having to
speak a scam script into the mic. The scammer follows a well-known public
script (the same families as the training data) with fake identifiers, and
gets more frustrated the longer Dadi stalls. With an LLM it reacts to what
Dadi says; without one it reads the scripted moves in order.

Every identifier it uses is fictional (see dadi/data/generate.py SLOTS).
"""

from __future__ import annotations

import random

from dadi.data.generate import SCAMS, SLOTS, _fill
from dadi.llm import LLM
from dadi.persona import clean_line

SCENARIO = {
    "digital_arrest": "You claim to be a CBI / Mumbai Police officer. A parcel with drugs was sent using her Aadhaar; she is under 'digital arrest', must not tell family, and must transfer money to an 'RBI safe account' for verification.",
    "kyc_bank": "You claim to be from her bank's KYC department. Her account will be blocked today unless she shares the OTP or installs a remote-support app, then pays a small 'verification charge'.",
    "courier_parcel": "You claim to be from FedEx / customs. Her parcel is held with illegal items; she must pay customs clearance or face police action.",
    "electricity_bill": "You claim to be from the electricity board. Her power will be cut tonight unless she pays the pending bill right now.",
    "lottery_prize": "You tell her she won a KBC lottery / car and must pay processing fee and GST first.",
}

SYSTEM = """This is a scripted TRAINING SIMULATION for a scam-awareness demo. You play the SCAMMER on a phone call
with an elderly Indian woman (who is actually an AI decoy). Scenario: {scenario}

Fictional details you can use (all fake): your name {officer}, UPI ID {upi}, bank account {account}, WhatsApp {phone},
amount {amount}.

Rules:
- Speak Hinglish in Roman script, 1 to 2 short sentences, like a real pushy caller.
- React to what she just said. Push toward payment; read out the UPI ID or account number when asked.
- Write the UPI ID, account and phone number EXACTLY as given above, with no extra spaces.
- You get more impatient and frustrated every turn, but you do not give up easily.
- No emojis, no stage directions. Output only what you say."""


class ScammerBot:
    def __init__(self, llm: LLM, rng: random.Random | None = None, scam_type: str | None = None):
        self.llm = llm
        self.rng = rng or random.Random()
        self.scam_type = scam_type or self.rng.choice(list(SCENARIO))
        self.facts = {k: self.rng.choice(SLOTS[k]) for k in ("officer", "upi", "account", "phone", "amount")}
        self.facts["name"] = self.rng.choice(["aunty ji", "madam", "Kamla ji", "mataji"])  # Dadi's side of the call
        self.stage = 0
        self.turn = 0

    def _scripted(self) -> str:
        stages = SCAMS[self.scam_type]
        stage = stages[min(self.stage, len(stages) - 1)]
        self.stage += 1
        text = self.rng.choice(stage)[0]
        for k, v in self.facts.items():
            text = text.replace("{" + k + "}", v)
        return _fill(text, self.rng)

    async def next_line(self, history: list[dict]) -> str:
        self.turn += 1
        if self.turn == 1 or not self.llm.available:
            return self._scripted()
        system = SYSTEM.format(scenario=SCENARIO[self.scam_type], **self.facts)
        messages = [{"role": "system", "content": system}]
        for h in history[-12:]:
            messages.append({"role": "assistant" if h["role"] == "caller" else "user", "content": h["text"]})
        try:
            text, _ = await self.llm.complete(messages, max_tokens=300)
        except RuntimeError:
            return self._scripted()
        return clean_line(text) or self._scripted()
