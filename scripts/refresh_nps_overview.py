"""Apply verified manual fund inputs without rerunning DART or changing holdings.

Run from the repository: python -m scripts.refresh_nps_overview [--write]
The two seed files must be updated from the official, matching-period tables first.
This is a manual repair helper, not a scheduled collector or a freshness heartbeat.
"""
import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
import math
from pathlib import Path

# Load only this offline module; collectors.__init__ loads unrelated data clients.
_spec = importlib.util.spec_from_file_location(
    "nps_overview_inputs", Path(__file__).resolve().parents[1] / "api/collectors/nps_holdings.py"
)
nps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nps)


def refresh(previous, fund, asset_mix, now):
    if not previous.get("holdings") or previous.get("count") != len(previous["holdings"]):
        raise ValueError("existing holdings missing or count mismatch")
    as_of = date.fromisoformat(fund["as_of"])
    if as_of < date.fromisoformat(previous["fund"]["as_of"]):
        raise ValueError("fund period would move backwards")
    if len(asset_mix) != 1 or asset_mix[0]["as_of"] != f"{as_of.year}년 {as_of.month}월":
        raise ValueError("fund and allocation periods differ")
    if fund.get("return_period_end") != fund["as_of"]:
        raise ValueError("return period differs from fund period")
    total = asset_mix[0]["total_bil"]
    if not math.isclose(total / 1000, fund["aum_krw_trillion"], abs_tol=0.0001):
        raise ValueError("fund and allocation AUM differ")
    rows = asset_mix[0]["mix"]
    if not rows or len({r["name"] for r in rows}) != len(rows):
        raise ValueError("allocation missing or duplicate categories")
    for r in rows:
        if not all(isinstance(r[k], (int, float)) and math.isfinite(r[k]) for k in ("amount_bil", "pct")):
            raise ValueError("allocation contains invalid numeric values")
    next_doc = deepcopy(previous)
    next_doc["fund"] = deepcopy(fund)
    next_doc["asset_mix"] = deepcopy(asset_mix)
    # Do not make an unchanged source look newly refreshed.
    if next_doc != previous:
        next_doc["generated_at"] = now
    return next_doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    path = Path(nps.OUTPUT_PATH)
    previous_bytes = path.read_bytes()
    previous = json.loads(previous_bytes)
    fund = json.loads(Path(nps.FUND_OVERVIEW_PATH).read_text())
    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    out = refresh(previous, fund, nps._asset_mix(), now)
    if args.write and out != previous:
        if path.read_bytes() != previous_bytes:
            raise RuntimeError("holdings changed during refresh; retry from current data")
        nps._write_json(str(path), out)
    print(json.dumps({
        "mode": "write" if args.write else "check",
        "fund_as_of": fund["as_of"], "asset_mix_as_of": out["asset_mix"][0]["as_of"],
        "holdings_preserved": len(out["holdings"]), "full_preserved": len(out.get("full", [])),
        "full_us_preserved": len(out.get("full_us", [])),
        "holdings_as_of_latest": out["as_of_latest"], "changed": out != previous,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
