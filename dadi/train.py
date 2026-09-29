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

from dadi.data.generate import generate, load_paraphrases
from dadi.detector import DEFAULT_EMBEDDER, DEFAULT_PATH, Detector, prefixes

ALERT = 0.8  # probability at which Dadi takes over the call


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
            type_true.append(call["scam_type"])
            type_pred.append(det.predict(full).scam_type)
            for turn in call["turns"]:
                tac_true.append(set(turn["tactics"]))
                tac_pred.append(set(det.tactics(turn["text"])))
        else:
            n_legit += 1
            legit_false_alarms += fired_at is not None

    y_arr, p_arr = np.array(y), np.array(p)
    caught = [t for t in detect_turns if t is not None]
    labels = det.tactic_labels
    tt = np.array([[l in s for l in labels] for s in tac_true])
    tp = np.array([[l in s for l in labels] for s in tac_pred])
    return {
        "prefix_roc_auc": round(float(roc_auc_score(y_arr, p_arr)), 4),
        "prefix_f1@0.5": round(float(f1_score(y_arr, p_arr >= 0.5)), 4),
        "prefix_precision@0.8": round(float(precision_score(y_arr, p_arr >= ALERT)), 4),
        "prefix_recall@0.8": round(float(recall_score(y_arr, p_arr >= ALERT)), 4),
        "call_scam_caught_rate": round(len(caught) / max(n_scam, 1), 4),
        "call_median_turns_to_detect": float(np.median(caught)) if caught else None,
        "call_caught_by_turn_2": round(sum(t <= 2 for t in caught) / max(n_scam, 1), 4),
        "call_legit_false_alarm_rate": round(legit_false_alarms / max(n_legit, 1), 4),
        "scam_type_accuracy": round(float(np.mean([a == b for a, b in zip(type_true, type_pred)])), 4),
        "tactics_micro_f1": round(float(f1_score(tt, tp, average="micro", zero_division=0)), 4),
        "tactics_per_label_f1": {l: round(float(f1_score(tt[:, i], tp[:, i], zero_division=0)), 4)
                                 for i, l in enumerate(labels)},
        "n_test_calls": len(calls),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--features", choices=["tfidf", "embed", "hybrid"], default="hybrid")
    ap.add_argument("--embedder", default=DEFAULT_EMBEDDER)
    ap.add_argument("--no-augment", action="store_true", help="ignore LLM paraphrases")
    args = ap.parse_args()

    train, test = generate(args.n, args.seed, augment=not args.no_augment)
    det = Detector.train(train, args.features, args.embedder)
    det.save(args.out)
    n_paras = sum(len(v) for v in load_paraphrases().values()) if not args.no_augment else 0
    metrics = {"features": args.features, "embedder": args.embedder if args.features != "tfidf" else None,
               "llm_paraphrases": n_paras,
               **evaluate(det, test)}
    metrics_path = args.out.parent / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    print(f"saved model to {args.out} and metrics to {metrics_path}")


if __name__ == "__main__":
    main()
