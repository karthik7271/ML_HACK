# Dadi: the AI grandma who scams the scammers

Indians lost **₹22,495 crore** to cyber fraud in 2025, and cases rose 24% ([ThePrint](https://theprint.in/india/cybercrime-saw-24-spike-in-2025-indians-lost-rs-22495-crore-mainly-in-investment-scams/2859930/)).
"Digital arrest" calls, fake KYC calls, and courier/customs threats all follow scripts.

**Dadi** answers those calls for you. She's a warm, rambling, slightly deaf 78-year-old from Lucknow who
keeps scammers on the line for as long as possible. While they talk, machine learning:

1. **detects the scam within the first sentence or two**, and hands genuine callers back to you;
2. **picks Dadi's next stalling move** with a bandit that learns which moves keep scammers talking and get them to reveal details;
3. **extracts the scammer's UPI IDs, phone numbers, bank accounts and IFSC codes**, even when they're read out aloud ("nine eight double seven…", "cbi dot safe at the rate paytm");
4. **links calls into scam rings** through shared mule accounts;
5. **drafts a cybercrime.gov.in complaint**. You review it and submit it yourself.

Every minute a scammer spends with Dadi is a minute they aren't scamming someone else.

## Quick start

```bash
uv sync
uv run python -m dadi.train          # generate data, train detector, write models/metrics.json
uv run python -m dadi.seed           # optional: simulated past calls so the network graph isn't empty
uv run uvicorn dadi.app:app --port 8765
```

Open http://localhost:8765 in **Chrome**, press **Incoming call**, and play the scammer: speak Hinglish into the
mic, or type. Dadi answers aloud.

Dadi works without any API key, using scripted lines. For LLM-written lines, copy `.env.example` to `.env` and
set `DADI_LLM_API_KEY`. Any OpenAI-compatible endpoint works; the default is Featherless.

## How it works

```
caller speech ──► browser speech-to-text (en-IN / hi-IN)
                        │ text over WebSocket
                        ▼
      ┌─────────── CallSession (dadi/session.py) ───────────┐
      │ 1. Detector: P(scam | transcript so far)            │  screening → engaged (≥0.8)
      │    + scam type + manipulation tactics               │            → handoff (<0.3 after 2 turns)
      │ 2. Extractor: spoken-number/UPI normalisation       │
      │ 3. Bandit: choose stalling move (Thompson sampling) │
      │ 4. Persona: LLM or scripted Hinglish line           │
      └──────────────────────────────────────────────────────┘
                        │
                        ▼
browser text-to-speech (Dadi's voice) + live dashboard
on hang-up: call saved → scam-network graph → cybercrime report draft
```

| Module | What it does |
|---|---|
| `dadi/data/generate.py` | Synthetic Hinglish scam and genuine-call transcripts (7 scam types, 9 kinds of genuine call, including hard negatives), with noise that imitates speech-to-text errors |
| `dadi/detector.py` | Char + word TF-IDF combined with multilingual MiniLM sentence embeddings, feeding three logistic-regression heads: scam/genuine, scam type, and tactics (multi-label) |
| `dadi/train.py` | Training plus evaluation on held-out phrasings, per turn and per call |
| `dadi/extract.py` | Normalises identifiers read out aloud (English/Hindi/Devanagari digits, "double", "at the rate"), then extracts them |
| `dadi/tactics.py` | Contextual Thompson-sampling bandit with a global prior shared across scam types |
| `dadi/persona.py` | Dadi's system prompt, the LLM call, and scripted lines used when the LLM is unavailable |
| `dadi/network.py` | Graph of calls and identifiers; connected components with 2+ calls become rings |
| `dadi/report.py` | Draft complaint for the National Cyber Crime Reporting Portal |

## Results (held-out synthetic set)

Test calls are built from **phrasings the model never saw in training**: each move's phrasings are split 75/25
before any calls are generated. See `models/metrics.json`.

| Features | ROC AUC | Precision @0.8 | Scams caught | False alarms (genuine calls) | Scam-type acc. | Tactics micro-F1 |
|---|---|---|---|---|---|---|
| TF-IDF only | 0.951 | 0.892 | 95.7% | 23.3% | 50.6% | 0.468 |
| Embeddings only | 0.868 | 0.859 | 89.5% | 27.6% | 70.8% | 0.591 |
| **Hybrid (default)** | 0.939 | **0.940** | 95.5% | **16.9%** | 63.0% | 0.532 |

The median scam is detected on the **first** caller utterance. Server-side latency per turn is about 20–60 ms on an M1 Pro.

**Known limitation:** the data is synthetic and has few phrasings per move, which drives the false-alarm rate.
Next steps: LLM paraphrase augmentation, and a role-played evaluation set recorded by volunteers.

## Safety and ethics

- **Answer-only:** Dadi never dials anyone. She only answers calls that reach her.
- **Never gives anything real:** no real money, personal details, OTPs or PINs. The prompt forbids it, and the
  scripted fallback lines contain none.
- **Nothing is filed automatically:** reports are drafts for the user to check and submit.
- **Local storage:** call records stay on the machine (`data/runtime/`). Seeded demo calls are flagged `seed: true`
  and drawn differently in the graph.

## Tests

```bash
uv run python -m pytest -q
```
