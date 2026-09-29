"""Dadi's voice: turns (tactic, conversation) into her next line.

When a free LLM provider is configured (see dadi/llm.py: Groq, Gemini,
OpenRouter or local Ollama), it writes the line, steered by the tactic the
bandit picked. With no provider, or if every provider is slow or failing, a
scripted fallback keeps the demo alive.
"""

from __future__ import annotations

import random
import re

from dadi.llm import LLM
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
- NEVER end or pause the call, never say you will call back later, never tell them to call someone else.
  Keep them talking: end most replies with a question or an unfinished thought.
- Call the caller "beta" (never "bhai", "sir" or "dude").
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
    def __init__(self, rng: random.Random | None = None, llm: LLM | None = None):
        self.rng = rng or random.Random()
        self.llm = llm if llm is not None else LLM()

    @property
    def mode(self) -> str:
        return f"llm: {self.llm.description}" if self.llm.available else "scripted"

    def screening_line(self) -> str:
        return self.rng.choice(SCREENING)

    def fallback(self, tactic: str, last_scammer_text: str) -> str:
        line = self.rng.choice(FALLBACK[tactic]).format(word=_pick_word(last_scammer_text))
        return line[0].upper() + line[1:]

    async def reply(self, tactic: str, history: list[dict], scam_type: str | None) -> tuple[str, str]:
        """Returns (line, source): source is the LLM provider name, or 'scripted'."""
        last = next((h["text"] for h in reversed(history) if h["role"] == "caller"), "")
        if not self.llm.available:
            return self.fallback(tactic, last), "scripted"
        word = _pick_word(last)
        examples = "\n".join(f"- {e.format(word=word)}" for e in self.rng.sample(FALLBACK[tactic], 2))
        system = (f"{SYSTEM_PROMPT}\n\nLikely scam type: {scam_type or 'unknown'}.\n"
                  f"Your move for THIS reply ({tactic}): {TACTICS[tactic]}\n"
                  f"Style examples for this move (do not copy them, react to what the caller just said):\n{examples}")
        messages = [{"role": "system", "content": system}]
        for h in history[-12:]:
            messages.append({"role": "user" if h["role"] == "caller" else "assistant", "content": h["text"]})
        try:
            text, provider = await self.llm.complete(messages, max_tokens=300)
        except RuntimeError:
            return self.fallback(tactic, last), "scripted"
        text = clean_line(text)
        return (text, provider) if text else (self.fallback(tactic, last), "scripted")


def clean_line(text: str) -> str:
    """Keep what Dadi would actually say: no speaker labels, quotes, stage directions, or essays."""
    text = re.sub(r"^\s*(dadi|kamla devi|kamla)\s*:\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"[*(\[][^*)\]]*[*)\]]", "", text)  # *sighs* (laughs) [pause]
    text = EMOJI_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s*", text) if x.strip()]
    return " ".join(list(dict.fromkeys(sentences))[:3])


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")
