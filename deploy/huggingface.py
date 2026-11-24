"""Publish RASID as a Hugging Face Docker Space (the hosted demo for the judges).

    pip install huggingface_hub
    hf auth login                       # your own write token, typed into your own terminal
    python deploy/huggingface.py <user>/rasid [--with-data]

Uploads the committed code (plus the local case database and screenshots with --with-data), and stores the
keys from .env as Space secrets, never in the Space's public files. A console password is created when .env
has none and printed once: give it to the judges.
"""
import argparse
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("presentation/", "deploy/", "tests/", ".gitignore")
SECRETS = ("ANTHROPIC_API_KEY", "GOOGLE_MAPS_API_KEY", "SERPAPI_KEY", "META_ACCESS_TOKEN", "GOOGLE_SAFE_BROWSING_KEY",
           "VIRUSTOTAL_API_KEY", "RASID_PASSWORD", "RASID_SESSION_SECRET")
HEADER = """---
title: RASID Scam Radar
emoji: 📡
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: true
short_description: Proactive radar for scam links, sites, ads and calls in the UAE
---

"""


def stage(dst: Path, with_data: bool) -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    for f in filter(None, files):
        if f.startswith(SKIP) or f.endswith((".pptx", ".pdf")):
            continue
        (dst / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dst / f)
    (dst / "README.md").write_text(HEADER + (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    if with_data and (ROOT / "data/rasid.db").exists():
        src, out = sqlite3.connect(ROOT / "data/rasid.db"), sqlite3.connect(dst / "data/rasid.db")
        src.backup(out)
        out.close(), src.close()
        if (ROOT / "data/shots").exists():
            shutil.copytree(ROOT / "data/shots", dst / "data/shots")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("space", help="<user>/<space-name>")
    ap.add_argument("--with-data", action="store_true", help="also upload the local cases and screenshots")
    args = ap.parse_args()
    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)

    env = {k: (v or "").strip() for k, v in dotenv_values(ROOT / ".env").items()}
    new_pw = not env.get("RASID_PASSWORD")
    env.setdefault("RASID_SESSION_SECRET", "")
    if new_pw:
        env["RASID_PASSWORD"] = "rasid-" + secrets.token_urlsafe(6)
    if not env["RASID_SESSION_SECRET"]:
        env["RASID_SESSION_SECRET"] = secrets.token_hex(32)
    for k in SECRETS:
        if env.get(k):
            api.add_space_secret(args.space, k, env[k])
    for k, v in (("RASID_GUARDIAN_REMOTE", "1"), ("RASID_MODEL", env.get("RASID_MODEL") or "claude-opus-5-5")):
        api.add_space_variable(args.space, k, v)

    with tempfile.TemporaryDirectory() as tmp:
        stage(Path(tmp), args.with_data)
        api.upload_folder(folder_path=tmp, repo_id=args.space, repo_type="space", commit_message="Deploy RASID")
    host = args.space.replace("/", "-").replace("_", "-").lower()
    print(f"Live URL: https://{host}.hf.space   (build takes ~5 minutes)")
    if new_pw:
        print(f"Console password for the judges: {env['RASID_PASSWORD']}")


if __name__ == "__main__":
    sys.exit(main())
