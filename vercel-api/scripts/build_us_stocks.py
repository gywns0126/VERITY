"""미국 주식 전종목 리스트 생성 → data/us_stocks.json (검색 자동완성용)

데이터 소스: NASDAQ Trader 공식 무료 파일 (API key 불필요, pipe-delimited)
  - nasdaqlisted.txt — NASDAQ 상장
  - otherlisted.txt — NYSE / NYSE American / NYSE Arca / BATS / IEX

기존 search.py US_STOCKS 73개의 name_kr 한글명은 ticker 매칭으로 보존.
"""
import json
import os
import re
import urllib.request

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

EXCHANGE_MAP = {
    "N": "NYSE",
    "A": "NYSE American",
    "P": "NYSE Arca",
    "Z": "BATS",
    "V": "IEX",
}

NOISE_PATTERNS = re.compile(
    r"(\bWarrants?\b|\bRights?\b|\bUnits?\b|% Notes due|Depositary Pref|Preferred Stock)",
    re.IGNORECASE,
)


def fetch(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", errors="replace")
    return text.splitlines()


def clean_name(raw: str) -> str:
    """'Apple Inc. - Common Stock' → 'Apple Inc.'"""
    s = raw.strip()
    if " - " in s:
        s = s.split(" - ")[0].strip()
    for suffix in (" Common Stock", " Ordinary Shares", " Capital Stock", " Class A", " Class B"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s[:80]


def parse_nasdaq(lines: list[str]) -> list[dict]:
    out = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 8:
            continue
        sym, name, _cat, test, _fin, _lot, etf, _nshare = parts[:8]
        if not sym or not name or test == "Y":
            continue
        if NOISE_PATTERNS.search(name):
            continue
        out.append({
            "ticker": sym,
            "name": clean_name(name),
            "market": "NASDAQ",
            "yf": sym.replace(".", "-"),
            "etf": etf == "Y",
        })
    return out


def parse_other(lines: list[str]) -> list[dict]:
    out = []
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 8:
            continue
        sym, name, exch, cqs, etf, _lot, test, _ndsym = parts[:8]
        if not sym or not name or test == "Y":
            continue
        if NOISE_PATTERNS.search(name):
            continue
        out.append({
            "ticker": sym.replace(".", "-"),
            "name": clean_name(name),
            "market": EXCHANGE_MAP.get(exch, exch or "NYSE"),
            "yf": (cqs or sym).replace(".", "-"),
            "etf": etf == "Y",
        })
    return out


def load_existing_korean_names() -> dict:
    """search.py 의 US_STOCKS 에서 ticker → name_kr 추출 (한글명 보존용)."""
    search_py = os.path.join(os.path.dirname(__file__), "..", "api", "search.py")
    if not os.path.exists(search_py):
        return {}
    with open(search_py, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(r'\{"ticker":\s*"([^"]+)",\s*"name":\s*"[^"]*",\s*"name_kr":\s*"([^"]*)"')
    return dict(pattern.findall(text))


def main() -> None:
    print("Fetching NASDAQ listed...")
    nasdaq = parse_nasdaq(fetch(NASDAQ_URL))
    print(f"  → {len(nasdaq)} entries")

    print("Fetching other listed (NYSE/American/Arca/BATS/IEX)...")
    other = parse_other(fetch(OTHER_URL))
    print(f"  → {len(other)} entries")

    kr_map = load_existing_korean_names()
    print(f"Preserving {len(kr_map)} Korean names from existing US_STOCKS")

    seen = set()
    merged = []
    for entry in nasdaq + other:
        t = entry["ticker"]
        if t in seen:
            continue
        seen.add(t)
        if t in kr_map:
            entry["name_kr"] = kr_map[t]
        merged.append(entry)

    merged.sort(key=lambda e: e["ticker"])

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "us_stocks.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)
    print(f"저장 완료: {len(merged)}개 → {out_path}")

    missing = [t for t in kr_map if t not in seen]
    if missing:
        print(f"기존 73 중 매칭 안 된 ticker {len(missing)}: {missing}")

    ionq = [e for e in merged if e["ticker"] == "IONQ"]
    print(f"IONQ sanity: {ionq[0] if ionq else 'NOT FOUND'}")


if __name__ == "__main__":
    main()
