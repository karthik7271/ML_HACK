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

Open http://localhost:8765 in **Chrome**. Then either:
- press **▶ Watch a demo call**, and an AI scammer (following a real scam script, with fake details) calls Dadi. Both
  speak aloud in neural Hindi voices; or
- press **Incoming call** and play the scammer yourself: speak Hinglish into the mic, or type.

Docker (the same image runs on Hugging Face Spaces):
```bash
docker build -t dadi . && docker run -p 7860:7860 --env-file .env dadi
```

Dadi works with **no API key**, using scripted lines. For LLM-written lines, copy `.env.example` to `.env` and
add a key for any **free** provider. Dadi tries them in order and moves to the next one on errors or rate limits:

| Provider | Free tier | Setup |
|---|---|---|
| Groq (default, fastest) | about 1,000 requests/day on gpt-oss / Qwen | `GROQ_API_KEY` from console.groq.com |
| Google Gemini | Flash-Lite, about 500 requests/day | `GEMINI_API_KEY` from aistudio.google.com |
| OpenRouter | `:free` models | `OPENROUTER_API_KEY` |
| Ollama (offline) | unlimited, runs locally | `ollama pull qwen2.5:3b` (no key needed) |

Check which providers work: `uv run python -m dadi.llm`

To add more training data (optional, uses the LLM):
`uv run python -m dadi.data.augment` writes paraphrases of every script line to `dadi/data/paraphrases.json`.
Then retrain with `uv run python -m dadi.train`.

## How it works

```
caller speech ──► browser speech-to-text (en-IN / hi-IN)
                        │ text over WebSocket
                        ▼
      ┌─────────── CallSession (dadi/session.py) ───────────┐
      │ 1. Detector: P(scam | transcript so far)            │  screening → engaged (≥0.85)
      │    + scam type + manipulation tactics               │            → handoff (<0.05 after 2 turns)
      │ 2. Extractor: spoken-number/UPI normalisation       │
      │ 3. Bandit: choose stalling move (Thompson sampling) │
      │ 4. Persona: LLM or scripted Hinglish line           │
      └──────────────────────────────────────────────────────┘
                        │
                        ▼
neural text-to-speech (Edge hi-IN voices, streamed; browser voice fallback) + live dashboard
on hang-up: call saved → scam-network graph → cybercrime report draft
```

| Module | What it does |
|---|---|
| `dadi/data/generate.py` | Synthetic Hinglish scam and genuine-call transcripts (7 scam types, 9 kinds of genuine call, including hard negatives), with noise that imitates speech-to-text errors |
| `dadi/detector.py` | Char + word TF-IDF combined with multilingual MiniLM sentence embeddings, feeding three logistic-regression heads: scam/genuine, scam type, and tactics (multi-label) |
| `dadi/train.py` | Training, call-policy thresholds tuned on a disjoint validation split, and evaluation on held-out phrasings |
| `dadi/extract.py` | Normalises identifiers read out aloud (English/Hindi/Devanagari digits, "double", "at the rate"), then extracts them |
| `dadi/tactics.py` | Contextual Thompson-sampling bandit with a global prior shared across scam types |
| `dadi/llm.py` | Access to free LLM providers (Groq, Gemini, OpenRouter, Ollama), with automatic fallback |
| `dadi/persona.py` | Dadi's system prompt, output cleanup, and scripted lines used when no LLM is available |
| `dadi/data/augment.py` | LLM paraphrases of each script line; each one stays on the same side of the train/test split as its source |
| `dadi/network.py` | Graph of calls and identifiers; connected components with 2+ calls become rings |
| `dadi/report.py` | Draft complaint for the National Cyber Crime Reporting Portal |
| `dadi/scammer.py` | Simulated scammer for demo calls (LLM-driven, or scripted without an LLM), using fake details only |
| `dadi/voice.py` | Streaming neural text-to-speech |
| `dadi/eval_roleplay.py` | Scores the detector on real role-played calls labelled in the app |

## Results (held-out synthetic set)

**How the test is kept honest:**
- Each move's hand-written phrasings are split 75/25 into train and test before any calls are generated.
- LLM paraphrases stay on the same side as the phrasing they came from, so every test call uses sentences the model
  never saw in training.
- The takeover (engage) and hand-back (handoff) thresholds are chosen on a separate validation split, disjoint from
  both train and test.
- The final model is then refit on train + validation.

Full numbers are in `models/metrics.json`.

**What matters in the app is the call outcome.** Dadi either takes the call over (**engaged**), hands it back to you
(**handoff**), or keeps politely screening. The worst mistake is handing a scammer to you.

| Model (same 1,000 test calls) | Scams engaged | **Scams handed to you** | **Genuine calls taken over** | ROC AUC | Precision @0.8 | Scam-type acc. |
|---|---|---|---|---|---|---|
| Day 1: 177 hand-written lines, fixed thresholds | 83.3% | 4.2% | 17.3% | 0.897 | 0.858 | 64.1% |
| **Final: + 1,271 LLM paraphrases + hard negatives + tuned thresholds** | 78.1% | **0.0%** | **2.3%** | **0.964** | **0.981** | **71.4%** |

The scams that aren't engaged stay in *screening*, where Dadi still stalls politely instead of handing the call over.
The median scam is detected on the **first** caller utterance. Per-turn server latency is about 20–60 ms for
detection, plus about 0.5–1 s for Dadi's LLM reply (Groq).

**How we got there:**
1. **Features.** On the first data, TF-IDF matched surface wording (AUC 0.951, but 23% false alarms) and
   embeddings captured meaning (70.8% scam-type accuracy). The hybrid combined both.
2. **Error analysis.** Most false alarms came from genuine police, bank-branch, college-fee and utility calls.
3. **More data.** We added hard negatives: genuine calls that send you to official channels ("come to the branch",
   "the bank never asks for OTP"). An LLM paraphrased every line 6 ways.
4. **Thresholds.** Engage and handoff thresholds were tuned on validation, with genuine calls taken over capped at 5%.

**Known limitations:**
- The data is synthetic. Real-world numbers will come from the role-play set below.
- The per-utterance tactic tagger is weak on rare tactics (OTP / PIN requests).

## Real-world evaluation (role-play)

The synthetic test set only measures phrasings we wrote ourselves. To test on real speech, volunteers play
scammers and genuine callers (family, delivery, bank branch) into the app. After each call, the operator labels it
in the transcript panel: **It was a scam** (with its type) or **It was genuine**. Labelled calls are saved to
`data/roleplay/labelled.jsonl`. Then:

```bash
uv run python -m dadi.eval_roleplay     # writes models/metrics_roleplay.json
```

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
