"""Deploy Dadi to a Hugging Face Space (Docker SDK, free CPU tier).

    HF_TOKEN=hf_... uv run python scripts/deploy_space.py --space <hf-username>/dadi

Uploads the repo (minus local data, .env and caches) with a Space README
header. Pass --copy-secrets to also store GROQ_API_KEY / GEMINI_API_KEY /
OPENROUTER_API_KEY from your local .env as private Space secrets; otherwise
add them yourself under Space → Settings → Variables and secrets. Without any
key the Space still works using Dadi's scripted lines.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEYS = ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY")
IGNORE = [".git/*", ".venv/*", ".env", "data/runtime/*", "data/synthetic/*", "**/__pycache__/*",
          ".pytest_cache/*", "*.pyc", ".DS_Store"]

HEADER = """---
title: Dadi, the AI grandma who scams the scammers
emoji: 👵
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
short_description: AI grandma that wastes scam callers' time and maps mule accounts
---

"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="e.g. your-hf-username/dadi")
    ap.add_argument("--copy-secrets", action="store_true", help="copy LLM keys from .env into Space secrets")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit("Set HF_TOKEN (huggingface.co → Settings → Access Tokens, 'write' scope).")
    api = HfApi(token=token)
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        readme = Path(tmp) / "README.md"
        readme.write_text(HEADER + (ROOT / "README.md").read_text())
        api.upload_folder(folder_path=str(ROOT), repo_id=args.space, repo_type="space",
                          ignore_patterns=IGNORE + ["README.md"], commit_message="Deploy Dadi")
        api.upload_file(path_or_fileobj=str(readme), path_in_repo="README.md", repo_id=args.space,
                        repo_type="space", commit_message="Space README")

    if args.copy_secrets:
        env = dotenv_values(ROOT / ".env")
        for key in SECRET_KEYS:
            if env.get(key):
                api.add_space_secret(args.space, key, env[key])
                print(f"secret set: {key}")

    print(f"Deployed. Build logs and app: https://huggingface.co/spaces/{args.space}")


if __name__ == "__main__":
    main()
