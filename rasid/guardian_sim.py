"""Try the Call Guardian without a phone: play a sample call through the same brain the voice agent uses.

    .venv\\Scripts\\python -m rasid.guardian_sim                  # every sample in data/sample_calls.json
    .venv\\Scripts\\python -m rasid.guardian_sim bank_otp_ar      # one sample
    .venv\\Scripts\\python -m rasid.guardian_sim --rules          # rules only, no Claude
"""
import asyncio
import json
import sys

from .config import ROOT
from .guardian import claude_ready
from .voice import simulate_call


def main(argv: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    use_claude = "--rules" not in argv and claude_ready()
    names = [a for a in argv if not a.startswith("--")]
    samples = {k: v for k, v in json.loads((ROOT / "data" / "sample_calls.json").read_text(encoding="utf-8")).items()
               if not k.startswith("_")}
    for name in names or list(samples):
        s = samples[name]
        out = asyncio.run(simulate_call(s["lines"], s["lang"], use_claude))
        print(f"\n=== {name}  ({'Claude + rules' if use_claude else 'rules only'}) ===")
        for step in out["timeline"]:
            print(f"  heard  [{step['risk']:3d}] {step['heard']}")
            for said in step["guardian_says"]:
                print(f"  RASID  >>> {said}")
        print(f"  verdict: {out['summary']['verdict']} (expected: {s.get('expect')})")
        print("  SMS:\n    " + out["sms"].replace("\n", "\n    "))


if __name__ == "__main__":
    main(sys.argv[1:])
