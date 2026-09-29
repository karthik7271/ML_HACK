"""Paraphrase every scripted move with a (free) LLM to widen the training data.

Each hand-written phrasing gets N paraphrases that keep its {slot}
placeholders. Paraphrases inherit their source's train/test pool in
generate.build_pools, so held-out evaluation stays leak-free.

Usage:  uv run python -m dadi.data.augment [--n 6]
Resumable: sources already in paraphrases.json are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from dotenv import load_dotenv

from dadi.data.generate import LEGIT, SCAMS
from dadi.llm import LLM

OUT = Path(__file__).resolve().parent / "paraphrases.json"
SLOT_RE = re.compile(r"\{[a-z_]+\}")

PROMPT = """You help build a dataset of Indian phone-call transcripts for training a scam-call detector.

Rewrite the line below in {n} different ways, the way different real callers in India would say it on the phone.
- Mix styles: casual Hinglish in Roman script, Indian English, more formal or more pushy, short or longer.
- Keep the same meaning and intent{intent}.
- Keep every placeholder in curly braces exactly as written, e.g. {example}.
- Return ONLY a JSON array of {n} strings.

Line: {line}"""


def sources() -> list[tuple[str, str]]:
    """(text, kind) for every scripted move."""
    out = []
    for stages in SCAMS.values():
        out += [(text, "scam") for stage in stages for text, _ in stage]
    for stages in LEGIT.values():
        out += [(text, "legit") for stage in stages for text in stage]
    return list(dict.fromkeys(out))


def parse(reply: str, source: str) -> list[str]:
    m = re.search(r"\[.*\]", reply, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    need = sorted(SLOT_RE.findall(source))
    keep = []
    for s in items:
        if isinstance(s, str) and sorted(SLOT_RE.findall(s)) == need and s.strip().lower() != source.lower():
            keep.append(s.strip())
    return list(dict.fromkeys(keep))


async def main_async(n: int, rpm: int) -> None:
    load_dotenv()
    llm = LLM(timeout=30)
    if not llm.available:
        raise SystemExit("No LLM provider configured. Set GROQ_API_KEY in .env (free at console.groq.com).")
    print(f"using {llm.description}")
    done: dict[str, list[str]] = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [(t, k) for t, k in sources() if t not in done]
    print(f"{len(done)} done, {len(todo)} to go")
    for i, (text, kind) in enumerate(todo, 1):
        intent = " (it is a SCAM caller line: keep the pressure and the scam intent)" if kind == "scam" else \
                 " (it is a GENUINE, harmless caller: keep it harmless)"
        prompt = PROMPT.format(n=n, line=text, intent=intent, example="{upi}")
        try:
            reply, provider = await llm.complete([{"role": "user", "content": prompt}], max_tokens=1500, temperature=1.0)
            paras = parse(reply, text)
        except RuntimeError as e:
            print(f"  [{i}/{len(todo)}] all providers failed: {e}; saving progress and stopping")
            break
        done[text] = paras
        OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1))
        print(f"  [{i}/{len(todo)}] {provider}: +{len(paras)}  {text[:60]}")
        await asyncio.sleep(60 / rpm)
    total = sum(len(v) for v in done.values())
    print(f"saved {total} paraphrases for {len(done)} source lines to {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="paraphrases per source line")
    ap.add_argument("--rpm", type=int, default=25, help="requests per minute (Groq free tier allows 30)")
    args = ap.parse_args()
    asyncio.run(main_async(args.n, args.rpm))


if __name__ == "__main__":
    main()
