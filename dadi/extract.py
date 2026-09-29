"""Pull scammer identifiers (UPI IDs, phone numbers, bank accounts, IFSC codes,
amounts, claimed authorities) out of noisy speech-to-text transcripts.

Scammers read identifiers aloud, so the transcript often contains
"nine eight seven double six ..." or "rahul at the rate ybl" instead of
clean strings. `normalize_spoken` rewrites those into canonical form before
the regexes run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DIGIT_WORDS = {
    # English
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Romanized Hindi
    "shunya": "0", "sunya": "0", "ek": "1", "do": "2", "teen": "3", "tin": "3",
    "char": "4", "chaar": "4", "paanch": "5", "panch": "5", "chhe": "6",
    "chhah": "6", "che": "6", "saat": "7", "aath": "8", "nau": "9",
    # Devanagari words
    "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5",
    "पाँच": "5", "छह": "6", "छः": "6", "सात": "7", "आठ": "8", "नौ": "9",
}
REPEAT_WORDS = {"double": 2, "triple": 3, "dabal": 2, "trible": 3}
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# A run of spoken digits must contain at least this many digits before we
# collapse it, so ordinary words like "do" / "one" in sentences survive.
MIN_SPOKEN_RUN = 4

AUTHORITIES = {
    "cbi": "CBI", "ed": "Enforcement Directorate", "enforcement directorate": "Enforcement Directorate",
    "police": "Police", "mumbai police": "Mumbai Police", "delhi police": "Delhi Police",
    "crime branch": "Crime Branch", "cyber cell": "Cyber Cell", "cyber crime": "Cyber Cell", "customs": "Customs",
    "narcotics": "Narcotics Bureau", "ncb": "Narcotics Bureau", "trai": "TRAI",
    "rbi": "RBI", "reserve bank": "RBI", "income tax": "Income Tax Dept",
    "fedex": "FedEx", "dhl": "DHL", "blue dart": "Blue Dart", "sbi": "SBI",
    "electricity board": "Electricity Board", "bijli vibhag": "Electricity Board",
    "supreme court": "Supreme Court", "high court": "High Court",
}

UPI_RE = re.compile(r"\b([a-z0-9][a-z0-9._-]{1,63}@[a-z]{2,20})\b(?!\.[a-z])", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91)?([6-9]\d{9})(?!\d)")
ACCOUNT_RE = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")
IFSC_RE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", re.I)
AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d+)?)"
    r"|([\d,]+(?:\.\d+)?)\s?(rupees|rupaye|rupay|rupiya|lakh|lac|crore|hazaar|hazar|thousand|k)\b",
    re.I,
)
NUMBER_WORD = r"(?:ek|do|dhai|teen|char|chaar|paanch|das|bees|pachaas|one|two|three|four|five|ten|twenty|fifty|hundred)"
WORD_AMOUNT_RE = re.compile(rf"\b({NUMBER_WORD}(?:\s{NUMBER_WORD})?)\s(lakh|lac|crore|hazaar|hazar|thousand)\b", re.I)
OFFICER_RE = re.compile(
    r"\b(?:inspector|officer|sub[- ]inspector|constable|dcp|acp|sp|agent)\s+([a-z]+(?:\s[a-z]+)?)",
    re.I,
)
OFFICER_STOPWORDS = {"hoon", "hu", "hai", "bol", "baat", "sir", "ji", "se", "from", "and", "speaking", "here"}


@dataclass
class Intel:
    upi_ids: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    ifsc: set[str] = field(default_factory=set)
    amounts: set[str] = field(default_factory=set)
    authorities: set[str] = field(default_factory=set)
    officer_names: set[str] = field(default_factory=set)

    IDENTIFIER_KINDS = ("upi_ids", "phones", "accounts", "ifsc")

    def merge(self, other: "Intel") -> "Intel":
        """Add other's items into self; return an Intel of only the new items."""
        new = Intel()
        for name in self.__dataclass_fields__:
            mine, theirs = getattr(self, name), getattr(other, name)
            getattr(new, name).update(theirs - mine)
            mine.update(theirs)
        return new

    def identifiers(self) -> list[tuple[str, str]]:
        """(kind, value) pairs that can link calls in the scam-network graph."""
        return [(kind, v) for kind in self.IDENTIFIER_KINDS for v in sorted(getattr(self, kind))]

    def is_empty(self) -> bool:
        return not any(getattr(self, name) for name in self.__dataclass_fields__)

    def to_dict(self) -> dict[str, list[str]]:
        return {name: sorted(getattr(self, name)) for name in self.__dataclass_fields__}


def _collapse_digit_runs(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        run: list[str] = []
        j = i
        while j < len(tokens):
            tok = tokens[j].lower().strip(",.")
            if tok in REPEAT_WORDS and j + 1 < len(tokens):
                nxt = tokens[j + 1].lower().strip(",.")
                digit = DIGIT_WORDS.get(nxt) or (nxt if re.fullmatch(r"\d", nxt) else None)
                if digit:
                    run.append(digit * REPEAT_WORDS[tok])
                    j += 2
                    continue
            if tok in DIGIT_WORDS:
                run.append(DIGIT_WORDS[tok])
            elif re.fullmatch(r"\d{1,5}", tok):
                run.append(tok)
            else:
                break
            j += 1
        consumed = j - i
        digits = "".join(run)
        if consumed and len(digits) >= MIN_SPOKEN_RUN:
            out.append(digits)
            i = j
        else:
            out.append(tokens[i])
            i += 1
    return out


def normalize_spoken(text: str) -> str:
    """Rewrite spoken-form identifiers into written form."""
    t = text.translate(DEVANAGARI_DIGITS)
    t = re.sub(r"\bat\s+the\s+rate(?:\s+of)?\b", "@", t, flags=re.I)
    t = re.sub(r"\bat\s+rate\b", "@", t, flags=re.I)
    t = re.sub(r"\s*@\s*", "@", t)
    # "rahul dot sharma@ybl" -> "rahul.sharma@ybl" (only when glued to an @ address)
    t = re.sub(r"\b(\w+)\s+dot\s+(\w+)(?=@)", r"\1.\2", t, flags=re.I)
    t = re.sub(r"\b(\w+)\s+underscore\s+(\w+)(?=@)", r"\1_\2", t, flags=re.I)
    tokens = _collapse_digit_runs(t.split())
    t = " ".join(tokens)
    # "98765 43210" -> "9876543210" when the pieces form a 10+ digit number
    t = re.sub(r"(?<=\d)[\s-](?=\d)", "", t)
    return t


def extract(text: str) -> Intel:
    t = normalize_spoken(text)
    intel = Intel()
    lowered = t.lower()

    for m in UPI_RE.finditer(t):
        intel.upi_ids.add(m.group(1).lower())

    phone_spans = []
    for m in PHONE_RE.finditer(t):
        intel.phones.add(m.group(1))
        phone_spans.append(m.span())

    for m in ACCOUNT_RE.finditer(t):
        if any(s <= m.start() < e for s, e in phone_spans):
            continue
        intel.accounts.add(m.group(1))

    for m in IFSC_RE.finditer(t):
        intel.ifsc.add(m.group(1).upper())

    for m in AMOUNT_RE.finditer(t):
        if m.group(1):
            intel.amounts.add(f"₹{m.group(1)}")
        else:
            intel.amounts.add(f"{m.group(2)} {m.group(3).lower()}")

    for m in WORD_AMOUNT_RE.finditer(t):
        intel.amounts.add(f"{m.group(1).lower()} {m.group(2).lower()}")

    for key, canonical in AUTHORITIES.items():
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            intel.authorities.add(canonical)
    if "Mumbai Police" in intel.authorities or "Delhi Police" in intel.authorities:
        intel.authorities.discard("Police")

    for m in OFFICER_RE.finditer(t):
        words = [w for w in m.group(1).split() if w.lower() not in OFFICER_STOPWORDS]
        if words:
            intel.officer_names.add(" ".join(w.capitalize() for w in words))

    return intel
