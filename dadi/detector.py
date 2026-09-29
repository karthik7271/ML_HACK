"""Streaming scam-call detector.

Three small models share one text featurizer (char + word TF-IDF, which is
robust to Hinglish spelling variation and ASR noise):

- scam vs. legit, scored on the caller's transcript *so far*, so Dadi can
  decide within the first few turns;
- scam type (digital arrest, KYC, courier, ...), for the dashboard and report;
- manipulation tactics per utterance (multi-label: authority, urgency, fear, ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "models" / "detector.joblib"
DEFAULT_EMBEDDER = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TACTIC_THRESHOLD = 0.5

_ENCODERS: dict[str, object] = {}
_CACHE: dict[tuple[str, str], np.ndarray] = {}


class SentenceEmbedder(BaseEstimator, TransformerMixin):
    """Multilingual sentence embeddings as sklearn features.

    Captures meaning ("apna OTP bataiye" ~ "share the code you received"),
    which TF-IDF misses on unseen phrasings. The encoder is loaded lazily and
    never pickled; embeddings are cached per process.
    """

    def __init__(self, model_name: str = DEFAULT_EMBEDDER):
        self.model_name = model_name

    def fit(self, X, y=None):
        return self

    def transform(self, X) -> np.ndarray:
        if self.model_name not in _ENCODERS:
            from sentence_transformers import SentenceTransformer
            _ENCODERS[self.model_name] = SentenceTransformer(self.model_name)
        missing = [x for x in dict.fromkeys(X) if (self.model_name, x) not in _CACHE]
        if missing:
            vecs = _ENCODERS[self.model_name].encode(missing, batch_size=64, normalize_embeddings=True)
            _CACHE.update({(self.model_name, x): v for x, v in zip(missing, vecs)})
        return np.vstack([_CACHE[(self.model_name, x)] for x in X])


def featurizer(kind: str = "hybrid", embedder: str = DEFAULT_EMBEDDER) -> FeatureUnion:
    parts = []
    if kind in ("tfidf", "hybrid"):
        parts += [
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)),
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, min_df=2)),
        ]
    if kind in ("embed", "hybrid"):
        parts.append(("embed", SentenceEmbedder(embedder)))
    return FeatureUnion(parts)


def prefixes(call: dict) -> list[str]:
    texts = [t["text"] for t in call["turns"]]
    return [" ".join(texts[: i + 1]) for i in range(len(texts))]


@dataclass
class Prediction:
    scam_prob: float
    scam_type: str | None
    type_probs: dict[str, float]


class Detector:
    # Call-policy and per-tactic thresholds, tuned on validation calls by dadi.train.
    engage_at = 0.8
    handoff_below = 0.3
    tactic_thresholds: dict[str, float] = {}

    def __init__(self, scam: Pipeline, scam_type: Pipeline, tactics: Pipeline, tactic_labels: list[str]):
        self.scam = scam
        self.scam_type = scam_type
        self.tactics_model = tactics
        self.tactic_labels = tactic_labels

    @classmethod
    def train(cls, calls: list[dict], features: str = "hybrid", embedder: str = DEFAULT_EMBEDDER) -> "Detector":
        X, y = [], []
        Xt, yt = [], []
        Xu, yu = [], []
        for call in calls:
            for p in prefixes(call):
                X.append(p)
                y.append(int(call["label"] == "scam"))
                if call["label"] == "scam":
                    Xt.append(p)
                    yt.append(call["scam_type"])
            for turn in call["turns"]:
                Xu.append(turn["text"])
                yu.append(turn["tactics"])

        scam = Pipeline([("f", featurizer(features, embedder)), ("clf", LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced"))])
        scam.fit(X, y)
        stype = Pipeline([("f", featurizer(features, embedder)), ("clf", LogisticRegression(C=4.0, max_iter=3000))])
        stype.fit(Xt, yt)
        mlb = MultiLabelBinarizer()
        Y = mlb.fit_transform(yu)
        tactics = Pipeline([("f", featurizer(features, embedder)),
                            ("clf", OneVsRestClassifier(LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced")))])
        tactics.fit(Xu, Y)
        return cls(scam, stype, tactics, list(mlb.classes_))

    def predict(self, transcript_so_far: str) -> Prediction:
        p = float(self.scam.predict_proba([transcript_so_far])[0][1])
        probs = self.scam_type.predict_proba([transcript_so_far])[0]
        type_probs = {c: float(v) for c, v in zip(self.scam_type.classes_, probs)}
        best = max(type_probs, key=type_probs.get)
        return Prediction(scam_prob=p, scam_type=best if p >= 0.5 else None, type_probs=type_probs)

    def tactics(self, utterance: str) -> dict[str, float]:
        probs = self.tactics_model.predict_proba([utterance])[0]
        return {t: float(v) for t, v in zip(self.tactic_labels, probs)
                if v >= self.tactic_thresholds.get(t, TACTIC_THRESHOLD)}

    def save(self, path: Path = DEFAULT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path = DEFAULT_PATH) -> "Detector":
        return joblib.load(path)
