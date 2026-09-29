"""Seed the call store with simulated past calls so the network graph has
something to show in a fresh demo. Seeded calls are flagged `seed: true` and
drawn differently in the UI. They are never presented as real data.

Usage:  uv run python -m dadi.seed [--n 14]
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

from dadi.data.generate import SCAM_TYPES, SLOTS
from dadi.session import CallStore

STORE = Path(__file__).resolve().parent.parent / "data" / "runtime" / "calls.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    store = CallStore(STORE)
    # A few "mule" identifiers that several fake officers reuse -> rings.
    mules = [{"upi_ids": [u]} for u in SLOTS["upi"][:3]] + [{"accounts": [a]} for a in SLOTS["account"][:2]]
    now = datetime.now()
    for i in range(args.n):
        intel = {"upi_ids": [], "phones": [f"{rng.choice("6789")}{rng.randint(10**8, 10**9 - 1)}"], "accounts": [], "ifsc": [],
                 "amounts": [rng.choice(SLOTS["amount"])], "authorities": [], "officer_names": []}
        mule = rng.choice(mules) if rng.random() < 0.8 else {"upi_ids": [f"user{rng.randint(100, 999)}@ybl"]}
        for k, v in mule.items():
            intel[k] += v
        store.add({
            "id": f"S{i:03d}",
            "seed": True,
            "started_at": (now - timedelta(hours=rng.randint(2, 200))).isoformat(timespec="seconds"),
            "scam_type": rng.choice(SCAM_TYPES),
            "scam_prob": round(rng.uniform(0.85, 0.99), 3),
            "wasted_s": rng.randint(120, 1800),
            "tactics": ["authority", "payment_request"],
            "dadi_moves": {},
            "intel": intel,
            "transcript": [],
        })
    print(f"seeded {args.n} simulated calls into {STORE}")


if __name__ == "__main__":
    main()
