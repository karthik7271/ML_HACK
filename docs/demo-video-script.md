# Demo video script (about 3 minutes)

**Recording setup:**
- Chrome full screen at `localhost:8765` (or the Space URL).
- Screen recorder with system audio on, so Dadi's and the scammer's voices are captured. On a Mac: QuickTime needs an
  audio loopback such as BlackHole; OBS also works.
- 1080p; hide the bookmarks bar.
- Before recording: run `uv run python -m dadi.seed` for a clean graph, and do one practice demo call so the models
  are warm.

| Time | On screen | Voice-over (you) |
|---|---|---|
| 0:00–0:12 | Black screen with the text "₹22,495 crore lost to cyber fraud in India in 2025", then fade to the Dadi header | "Last year Indians lost over twenty-two thousand crore rupees to scam calls: fake CBI officers, fake bank KYC, fake courier customs." |
| 0:12–0:22 | Dadi's avatar and card | "Blocking a number doesn't help. The scammer just calls the next grandmother. So we built one who can't be scammed." |
| 0:22–1:25 | Click **▶ Watch a demo call** → **Digital arrest**. Let 4–5 exchanges play with real audio. Zoom in on the gauge jumping to about 100%, the "Digital arrest" label, the tactic chips lighting up, and the UPI ID appearing in Captured intel | Mostly silent: let the call be the comedy. One line over the top: "Dadi decides within the first sentence that this is a scam, then her job is to waste his time." |
| 1:25–1:45 | Point at **Dadi's brain** bars and the move label under each reply | "Each reply is a stalling move chosen by a Thompson-sampling bandit. It learns which moves keep scammers talking, and which make them reveal their UPI IDs and accounts." |
| 1:45–2:05 | The scammer hangs up in frustration. Scroll to **Scam network** and hover over a ring | "When he gives up, the call joins our scam network. Different fake officers, same mule account. That's a ring." |
| 2:05–2:20 | Click **Draft cybercrime.gov.in report** and scroll the draft | "And the user gets a ready complaint for cybercrime.gov.in with every identifier. Nothing is filed automatically, and Dadi never shares real details." |
| 2:20–2:45 | Show the README results table, or a simple slide with the two key numbers | "We had no real data, so we built our own: 235 script lines, 1,271 LLM paraphrases, and a test set of phrasings the model never saw. Zero scams handed to the user, and only 2.3% of genuine calls taken over." |
| 2:45–2:55 | Quick live clip: you say one genuine line ("Hello mummy, main Rohit…") and Dadi hands the call back | "Real family calls go straight back to you." |
| 2:55–3:05 | End card: Dadi logo, GitHub URL, Space URL | "Dadi. Every minute with her is a minute a scammer isn't calling someone else." |

**Tips:**
- If the free LLM is slow on recording day, the scripted fallback still works. Just record several takes.
- Record the voice-over separately, then lay it over the screen recording in any editor (CapCut, iMovie).
- Upload to YouTube as **Unlisted** or public, and paste the link into Devpost.
