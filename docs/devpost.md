# Devpost submission: paste-ready text

Copy each section into the matching Devpost field. The numbers match `models/metrics.json`; if you retrain, update
them. Fill in the `TODO` items before submitting.

---

## Project name
**Dadi: the AI grandma who scams the scammers**

## Tagline (one line)
An AI grandmother who answers scam calls, wastes scammers' time in Hinglish, and turns every call into evidence
against the mule accounts behind them.

## Inspiration
Indians lost **₹22,495 crore** to cyber fraud in 2025, and cases rose 24%. "Digital arrest" calls, fake KYC calls
and courier-customs threats all follow scripts, and they work because victims are alone, scared and rushed. Most
defences only block a number, and the scammer simply dials the next person.

We asked a different question: what if the scammer's next call was to someone who could never be scammed, and who
kept them on the line for as long as possible? Every minute a scammer spends talking to Dadi is a minute they aren't
scamming someone's real grandmother.

## What it does
Dadi (Kamla Devi, 78, Lucknow, slightly hard of hearing, infinite stories) answers the call and:

1. **Detects the scam within the first sentence or two.** A streaming classifier scores the growing transcript, and
   genuine callers (family, delivery, bank branch, police verification) are handed back to you.
2. **Wastes the scammer's time.** She mishears, hunts for her glasses, gets confused by "OOPI", and tells long stories
   about her grandson's wedding. A learning algorithm (a Thompson-sampling bandit) chooses her next stalling move based
   on what has kept real scammers on the line.
3. **Collects their details.** UPI IDs, phone numbers, bank accounts and IFSC codes are pulled from speech, even when
   read out aloud ("nine eight double seven…", "cbi dot safe at the rate paytm").
4. **Maps scam rings.** Calls that share a UPI ID or mule account are linked into a live network graph.
5. **Drafts a cybercrime.gov.in complaint** for you to review and file. It also points to helpline 1930 and the
   Sanchar Saathi Chakshu portal.

The live dashboard shows the scam probability, the scam type, the manipulation tactics detected (fake authority,
urgency, OTP requests, secrecy…), the details captured, and a "scammer time wasted" counter.

**▶ Watch a demo call:** anyone can watch an AI scammer (following a real, publicly reported script, with fake
details) try to scam Dadi. Both speak aloud in neural Hindi voices.

## How we built it
- **Data.** No labelled Indian scam-call transcripts are public. We wrote 235 script lines covering 7 scam types
  (digital arrest, bank/KYC, courier, task-job, investment, electricity bill, lottery) and 10 kinds of genuine call.
  These include **hard negatives**: genuine bank, police and college-fee calls that sound similar but send you to
  official channels. An LLM (free Groq tier) paraphrased each line 6 ways, giving **1,271 paraphrases**. We added noise
  that imitates speech-to-text errors.
- **Honest evaluation.** Phrasings are split into train, validation and test **before** calls are generated, and each
  paraphrase stays on the same side as its source. So the test only contains sentences the model never saw.
- **Detector.** Character and word TF-IDF, combined with multilingual MiniLM sentence embeddings, feeding three
  heads: scam/genuine (on the transcript so far), scam type, and multi-label manipulation tactics. The thresholds for
  taking over or handing back a call, and a threshold for each tactic, are tuned on the validation split. The final
  model is refit on train + validation.
- **Dadi's brain.** A contextual Thompson-sampling bandit over 7 stalling moves, with a shared global prior across scam
  types. Reward: the scammer kept talking, plus a bonus when they revealed a new identifier.
- **Voice loop.** Browser speech-to-text (en-IN / hi-IN) → FastAPI WebSocket → detector, extractor and bandit → LLM
  persona (Groq, falling back to Gemini, then scripted lines) → streamed neural text-to-speech (Edge hi-IN voices).
- **Intel and graph.** A normaliser for spoken digits and UPI IDs (English, Romanised Hindi, Devanagari) plus regexes;
  NetworkX connected components to find scam rings; a complaint generator.
- **Deploy.** Docker on Hugging Face Spaces.

## Results (1,000 held-out test calls with unseen phrasings)
| | Day 1 | Final |
|---|---|---|
| Scams handed to the user by mistake | 4.2% | **0.0%** |
| Genuine calls taken over by Dadi | 17.3% | **2.3%** |
| ROC AUC (per turn) | 0.897 | **0.964** |
| Precision at the 0.8 threshold | 0.858 | **0.981** |
| Scam-type accuracy | 64.1% | **71.4%** |
| Tactic micro-F1 | 0.449 | **0.711** |

The median scam is detected on the **first** caller sentence. Detection takes about 20–60 ms per turn, and Dadi's LLM
reply about 0.5–1 s.

TODO: add the role-play results (`models/metrics_roleplay.json`) once friends have played scammers and genuine callers.

## Challenges we ran into
- **No real data.** We built a generator whose train/test split is by phrasing, so the model couldn't simply memorise
  our templates.
- **Our own evaluation bugs.** We caught a validation split that leaked training phrasings (it made the thresholds look
  far better than they were), and a random-number bug that made every test call identical. We fixed both and
  re-measured.
- **False alarms on genuine calls.** Error analysis showed genuine police, bank-branch and fee calls triggering Dadi.
  Hard-negative scripts plus threshold tuning took false alarms from 17% to 2.3% without handing any scammer to the
  user.
- **Real-time voice.** Keeping the reply loop under about a second meant a fast free LLM, streamed text-to-speech, and
  timeouts so a stalled audio clip never freezes a call.

## Accomplishments that we're proud of
- **Zero scams handed to the user** on the test set, while genuine callers are mostly handed back.
- A persona that is genuinely funny and still keeps collecting identifiers.
- Every call becomes evidence: the scam-ring graph plus a ready-to-file complaint.
- Runs entirely on free tiers, and still works (with scripted lines) with no API key at all.

## What we learned
- A good-looking metric means little until you check how the split was made.
- In safety tools, the cost of each mistake matters more than accuracy. Handing a scammer to a real person is far worse
  than Dadi politely stalling a genuine caller.
- Bandits are a clean way to make a persona learn from its conversations.

## What's next
- A pilot with telecom call-forwarding: forward suspected scam numbers to Dadi instead of just blocking them.
- Sharing the mule UPI IDs and accounts Dadi collects with I4C's suspect registry.
- More Indian languages (Tamil, Bengali, Marathi) and a Devanagari speech-to-text path.
- A real-call evaluation set with a partner NGO or cyber cell.

## Built with
python, fastapi, websockets, scikit-learn, sentence-transformers, pytorch, networkx, groq, gemini, edge-tts,
web-speech-api, d3.js, docker, hugging-face-spaces

## Links
- Code: https://github.com/karthik7271/ML_HACK
- Live demo: TODO (Hugging Face Space URL)
- Video: TODO (YouTube / Vimeo URL)

## Team
TODO: names and roles of each member. All members must be high-school or college students.
