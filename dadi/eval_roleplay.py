"""Score the detector on real role-played calls labelled in the app.

Friends play scammers and genuine callers; after each call the operator
labels it (scam + type, or genuine). Labelled calls are saved to
data/roleplay/labelled.jsonl, which is the real-world test set.

Usage:  uv run python -m dadi.eval_roleplay
"""

from __future__ import annotations

import json
from pathlib import Path

from dadi.detector import DEFAULT_PATH, Detector
from dadi.train import evaluate

ROLEPLAY = Path(__file__).resolve().parent.parent / "data" / "roleplay" / "labelled.jsonl"


def load() -> list[dict]:
    if not ROLEPLAY.exists():
        return []
    with open(ROLEPLAY) as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    calls = [c for c in load() if c["turns"]]
    if not calls:
        raise SystemExit(f"No labelled calls yet in {ROLEPLAY}. Label calls in the app after they end.")
    metrics = evaluate(Detector.load(DEFAULT_PATH), calls)
    out = DEFAULT_PATH.parent / "metrics_roleplay.json"
    out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    print(f"saved to {out}")


if __name__ == "__main__":
    main()
