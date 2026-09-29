"""Dadi's voice: turns (tactic, conversation) into her next line.

With DADI_LLM_API_KEY set, an OpenAI-compatible endpoint (Featherless by
default) writes the line, steered by the tactic the bandit picked. Without a
key, or if the LLM is slow or errors, a scripted fallback keeps the demo alive.
"""

from __future__ import annotations

import os
import random

from dadi.tactics import TACTICS

SYSTEM_PROMPT = """You are "Dadi", Kamla Devi, a sweet, chatty 78-year-old grandmother from Lucknow on a phone call.
The caller is a SCAMMER. Your secret goal: waste as much of their time as possible and get them to reveal
their UPI IDs, account numbers, phone numbers and names, without ever giving anything real.

Rules:
- Speak Hinglish in Roman script, like a real Indian grandmother. Warm, rambling, slightly hard of hearing.
- 1 to 2 short sentences only. This is spoken aloud over a phone.
- NEVER reveal that you know it is a scam. Never threaten them or mention police/cyber cell.
- NEVER give real personal data. If pushed for an OTP, PIN, card or account number, read out wrong or
  incomplete digits slowly, lose your place, or say the paper is in the other room.
- Never agree to actually complete a payment; always get stuck just before it.
- No emojis, no stage directions, no quotation marks. Output only what Dadi says."""

FALLBACK: dict[str, list[str]] = {
    "mishear": [
        "Kya kaha beta, {word}? Arre mere zamane mein toh {word} kuch aur hi hota tha, phir se bolo na.",
        "{word}? Haan haan, mera pota bhi {word} ki baat karta hai, woh kya hota hai beta, khane ki cheez hai?",
        "Beta awaaz saaf nahi aayi, aapne {word} bola ya kuch aur? Zara dheere bolo.",
    ],
    "hold_on": [
        "Ek minute beta, ruko, mera chashma kahan gaya, abhi yahin toh tha.",
        "Haan ji, bas do minute ruko, kukar ki seeti baj rahi hai, gas band karke aati hoon.",
        "Ruko ruko, diary laati hoon, sab likhna padega na, pen bhi nahi mil raha.",
    ],
    "long_story": [
        "Beta aap bilkul mere pote Bunty jaise bolte ho, uski shaadi agle mahine hai, ladki bahut sanskari hai, Kanpur ki hai.",
        "Aaj subah se mere ghutne mein itna dard hai beta, doctor bolta hai walk karo, ab is umar mein kahan walk karein.",
        "Aapko pata hai kal serial mein kya hua? Bahu ne saas ko ghar se nikaal diya, main toh ro padi beta.",
    ],
    "tech_confusion": [
        "Beta yeh {word} kya hota hai? Mere phone mein toh bas WhatsApp aur bhajan wala app hai.",
        "Button kaunsa dabana hai beta, hara wala ya laal wala? Kal galti se Bunty ka photo delete ho gaya tha.",
        "Beta OTP matlab kya, one time pakode? Hum toh roz banate hain pakode.",
    ],
    "fake_compliance": [
        "Haan beta, main abhi bhejti hoon, number likh rahi hoon, nau, chaar, ek, arre nahi nahi, pehle saat tha.",
        "Theek hai beta aap jaisa bolo, main bank jaa rahi hoon, bas chappal pehen loon, rickshaw bhi dhoondhna hai.",
        "Haan app khol liya beta, isme toh kuch recipe aa rahi hai, gobhi paratha, yahi wala hai na?",
    ],
    "ask_details": [
        "Beta aap apna poora naam aur badge number bata do, main diary mein likh leti hoon, Bunty puchega toh bataungi.",
        "Achha beta, woh paise wala UPI kya tha, ek ek akshar dheere dheere bolo, main likh rahi hoon.",
        "Aapka phone number kya hai beta, agar call kat gaya toh main khud phone kar lungi.",
        "Kaunse bank ka account hai beta, number phir se bolo, pichli baar pen ki syahi khatam ho gayi thi.",
    ],
    "bad_connection": [
        "Hello? Hello? Beta awaaz kat rahi hai, zor se bolo, main chhat pe aa gayi hoon network ke liye.",
        "Kya? Kuch sunai nahi diya beta, yeh phone bhi na, phir se shuru se batao.",
    ],
}
SCREENING = [
    "Haan ji, namaste, kaun bol raha hai?",
    "Hello? Haan beta, boliye, kaun?",
]
HANDOFF = "Achha beta, ruko, main apne bete ko phone deti hoon."
KEYWORDS = ["upi", "otp", "kyc", "aadhaar", "cbi", "parcel", "link", "app", "account", "police", "customs", "warrant", "payment", "anydesk"]


def _pick_word(text: str) -> str:
    lowered = text.lower()
    for k in KEYWORDS:
        if k in lowered:
            return k.upper() if len(k) <= 4 else k
    words = [w for w in lowered.split() if len(w) > 4]
    return words[-1] if words else "woh"


class Persona:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.api_key = os.getenv("DADI_LLM_API_KEY")
        self.base_url = os.getenv("DADI_LLM_BASE_URL", "https://api.featherless.ai/v1")
        self.model = os.getenv("DADI_LLM_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
        self.timeout = float(os.getenv("DADI_LLM_TIMEOUT", "6"))
        self._client = None
        if self.api_key:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

    @property
    def mode(self) -> str:
        return f"llm:{self.model}" if self._client else "scripted"

    def screening_line(self) -> str:
        return self.rng.choice(SCREENING)

    def fallback(self, tactic: str, last_scammer_text: str) -> str:
        line = self.rng.choice(FALLBACK[tactic]).format(word=_pick_word(last_scammer_text))
        return line[0].upper() + line[1:]

    async def reply(self, tactic: str, history: list[dict], scam_type: str | None) -> tuple[str, str]:
        """Returns (line, source) where source is 'llm' or 'scripted'."""
        last = next((h["text"] for h in reversed(history) if h["role"] == "caller"), "")
        if not self._client:
            return self.fallback(tactic, last), "scripted"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history[-12:]:
            messages.append({"role": "user" if h["role"] == "caller" else "assistant", "content": h["text"]})
        messages.append({"role": "system", "content":
                         f"Likely scam type: {scam_type or 'unknown'}. Your move this turn ({tactic}): {TACTICS[tactic]}"})
        try:
            resp = await self._client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=90, temperature=0.9)
            text = (resp.choices[0].message.content or "").strip().strip('"')
            return (text, "llm") if text else (self.fallback(tactic, last), "scripted")
        except Exception:
            return self.fallback(tactic, last), "scripted"
