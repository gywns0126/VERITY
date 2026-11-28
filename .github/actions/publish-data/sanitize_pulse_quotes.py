"""Remove unverified domestic prices from the staged *public* pulse."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from api.utils.kr_pulse_quote import KST, publishable_quotes, read_listings


def sanitize(pulse, listed, now):
    prices = pulse.get("prices") or {}
    verified = publishable_quotes(pulse, listed, now)
    for ticker in list(prices):
        domestic = ticker in listed or re.fullmatch(r"[0-9]{1,6}|[0-9][A-Z0-9]{5}", ticker)
        if domestic and ticker not in verified:
            del prices[ticker]
    pulse["prices"] = prices
    pulse["kr_quotes"] = verified
    pulse.setdefault("counts", {})["kr"] = len(verified)


if __name__ == "__main__":
    path = Path(sys.argv[1])
    pulse = json.loads(path.read_text(encoding="utf-8"))
    sanitize(pulse, read_listings(), datetime.now(KST))
    path.write_text(json.dumps(pulse, ensure_ascii=False), encoding="utf-8")
