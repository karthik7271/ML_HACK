"""Train the scam detector and write evaluation metrics.

Usage:  uv run python -m dadi.train [--n 4000]

Metrics are computed on held-out calls built from phrasings the model never
saw in training (see dadi/data/generate.py), and reported per turn prefix,
because the detector runs on a live, growing transcript.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

from dadi.data.generate import generate_splits, load_paraphrases
from dadi.detector import DEFAULT_EMBEDDER, DEFAULT_PATH, Detector, prefixes
from dadi.session import MIN_SCREEN_TURNS

ALERT = 0.8  # fixed threshold for the per-prefix precision/recall metrics
MAX_FALSE_ALARM = 0.05  # at most 5% of genuine calls may be taken over by Dadi (on validation)


def call_outcome(probs: list[float], engage_at: float, handoff_below: float) -> str:
    """Mirror of CallSession's policy: engage, hand back to the user, or keep screening."""
    for i, p in enumerate(probs, 1):
        if p >= engage_at:
            return "engaged"
        if i >= MIN_SCREEN_TURNS and p < handoff_below:
            return "handoff"
    return "screening"


def policy_rates(scored: list[tuple[str, list[float]]], engage_at: float, handoff_below: float) -> dict:
    out = {"scam": {"engaged": 0, "handoff": 0, "screening": 0}, "legit": {"engaged": 0, "handoff": 0, "screening": 0}}
    for label, probs in scored:
        out[label][call_outcome(probs, engage_at, handoff_below)] += 1
    n = {k: max(sum(v.values()), 1) for k, v in out.items()}
    return {
        "scam_engaged": round(out["scam"]["engaged"] / n["scam"], 4),
        "scam_handed_to_user": round(out["scam"]["handoff"] / n["scam"], 4),
        "legit_false_alarm": round(out["legit"]["engaged"] / n["legit"], 4),
        "legit_handed_back": round(out["legit"]["handoff"] / n["legit"], 4),
    }


def score_calls(det: Detector, calls: list[dict]) -> list[tuple[str, list[float]]]:
    return [(c["label"], [det.predict(p).scam_prob for p in prefixes(c)]) for c in calls]


def choose_thresholds(scored: list[tuple[str, list[float]]]) -> tuple[float, float, dict]:
    """Pick (engage_at, handoff_below) on validation calls: keep false alarms under
    MAX_FALSE_ALARM, then hand as few scammers to the user as possible, then
    engage as many scammers as possible, then hand back as many genuine callers."""
    best = None
    for e in [x / 100 for x in range(50, 100, 5)]:
        for h in [x / 100 for x in range(5, 45, 5)]:
            if h >= e:
                continue
            r = policy_rates(scored, e, h)
            if r["legit_false_alarm"] > MAX_FALSE_ALARM:
                continue
            key = (-r["scam_handed_to_user"], r["scam_engaged"], r["legit_handed_back"])
            if best is None or key > best[0]:
                best = (key, e, h, r)
    if best is None:
        return 0.95, 0.05, policy_rates(scored, 0.95, 0.05)
    return best[1], best[2], best[3]


def evaluate(det: Detector, calls: list[dict]) -> dict:
    y, p = [], []
    detect_turns, legit_false_alarms = [], 0
    type_true, type_pred = [], []
    tac_true, tac_pred = [], []
    n_scam = n_legit = 0

    for call in calls:
        is_scam = call["label"] == "scam"
        fired_at = None
        for i, prefix in enumerate(prefixes(call)):
            prob = det.predict(prefix).scam_prob
            y.append(int(is_scam))
            p.append(prob)
            if fired_at is None and prob >= ALERT:
                fired_at = i + 1
        if is_scam:
            n_scam += 1
            detect_turns.append(fired_at)
            full = " ".join(t["text"] for t in call["turns"])
            if call.get("scam_type"):
                type_true.append(call["scam_type"])
                type_pred.append(det.predict(full).scam_type)
            for turn in call["turns"]:
                if "tactics" in turn:  # role-played calls have no per-turn tactic labels
                    tac_true.append(set(turn["tactics"]))
                    tac_pred.append(set(det.tactics(turn["text"])))
        else:
            n_legit += 1
            legit_false_alarms += fired_at is not None

    y_arr, p_arr = np.array(y), np.array(p)
    caught = [t for t in detect_turns if t is not None]
    labels = det.tactic_labels
    tt = np.array([[l in s for l in labels] for s in tac_true]).reshape(-1, len(labels))
    tp = np.array([[l in s for l in labels] for s in tac_pred]).reshape(-1, len(labels))
    both_classes = len(set(y)) == 2
    metrics = {
        "prefix_roc_auc": round(float(roc_auc_score(y_arr, p_arr)), 4) if both_classes else None,
        "prefix_f1@0.5": round(float(f1_score(y_arr, p_arr >= 0.5)), 4),
        "prefix_precision@0.8": round(float(precision_score(y_arr, p_arr >= ALERT)), 4),
        "prefix_recall@0.8": round(float(recall_score(y_arr, p_arr >= ALERT)), 4),
        "call_scam_caught_rate": round(len(caught) / max(n_scam, 1), 4),
        "call_median_turns_to_detect": float(np.median(caught)) if caught else None,
        "call_caught_by_turn_2": round(sum(t <= 2 for t in caught) / max(n_scam, 1), 4),
        "call_legit_false_alarm_rate": round(legit_false_alarms / max(n_legit, 1), 4),
        "scam_type_accuracy": round(float(np.mean([a == b for a, b in zip(type_true, type_pred)])), 4) if type_true else None,
        "n_test_calls": len(calls),
        "n_scam_calls": n_scam,
        "n_legit_calls": n_legit,
    }
    if tac_true:
        metrics["tactics_micro_f1"] = round(float(f1_score(tt, tp, average="micro", zero_division=0)), 4)
        metrics["tactics_per_label_f1"] = {l: round(float(f1_score(tt[:, i], tp[:, i], zero_division=0)), 4)
                                           for i, l in enumerate(labels)}
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--features", choices=["tfidf", "embed", "hybrid"], default="hybrid")
    ap.add_argument("--embedder", default=DEFAULT_EMBEDDER)
    ap.add_argument("--no-augment", action="store_true", help="ignore LLM paraphrases")
    args = ap.parse_args()

    splits = generate_splits(args.n, args.seed, augment=not args.no_augment, val_frac=0.2)
    det = Detector.train(splits["train"], args.features, args.embedder)
    engage_at, handoff_below, val_policy = choose_thresholds(score_calls(det, splits["val"]))
    # Thresholds are fixed now; refit on train + validation for the final model.
    det = Detector.train(splits["train"] + splits["val"], args.features, args.embedder)
    det.engage_at, det.handoff_below = engage_at, handoff_below
    det.save(args.out)
    test = splits["test"]
    n_paras = sum(len(v) for v in load_paraphrases().values()) if not args.no_augment else 0
    metrics = {"features": args.features, "embedder": args.embedder if args.features != "tfidf" else None,
               "llm_paraphrases": n_paras,
               "engage_at": det.engage_at, "handoff_below": det.handoff_below,
               "policy_validation": val_policy,
               "policy_test": policy_rates(score_calls(det, test), det.engage_at, det.handoff_below),
               **evaluate(det, test)}
    metrics_path = args.out.parent / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    print(f"saved model to {args.out} and metrics to {metrics_path}")


if __name__ == "__main__":
    main()
