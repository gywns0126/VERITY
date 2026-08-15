#!/usr/bin/env python3
"""귀속·신선도 감사 — 2026-08-15 신설 (PM 지시).

**왜 스크립트인가.** 2026-08-15 하루에 귀속 결함 7건 + 신선도 결함 1건이 나왔는데,
전부 내가 손으로 찾았다. 손으로 찾는 건 다음 달에 반복되지 않는다. 그날 쓴 검사들을
기계로 옮겨 매달 자가 신고하게 한다.

**공통 형태 = 조용한 실패.** 여기서 잡는 것들은 에러도 경보도 워크플로 실패도 내지 않는다.
숫자가 그럴듯하게 틀려 있을 뿐이라 기존 신호로는 영구 미탐지다. 그래서 "값이 이상한가" 를
**명시적으로** 묻는 검사가 따로 있어야 한다.

검사 6종:
  ① 유니버스 이탈 화석 — 재수집 경로가 없어 옛 오답이 영구 잔존 (33종목 실측)
  ② Form 144 주당 환산 이상치 — 제출인 기입 오류 (SYF $25.27B, 실제 $25.7M)
  ③ 내부자 순증감 규모 — 발행주식 대비 비율 (VWAV 140배 = SVRE 거래 오귀속)
  ④ 발행사 귀속 표본 대조 — Form 4 원문 issuer CIK 가 우리 종목인가
  ⑤ 이름맵 신선도 — 생성 시각 사이드카 + git 커밋 이력 (CI mtime 함정)
  ⑥ 13D/G 커버리지 — EDGAR 실제 건수 대비 포착률 (죽은 폼명 필터 탐지)

③④⑥ 은 SEC 실호출이라 표본 상한을 둔다. ①②⑤ 는 파일·git 만 읽어 비용 0.

사용:
    python3 scripts/audit_attribution_freshness.py            # 전체
    python3 scripts/audit_attribution_freshness.py --no-net   # API 0 (①②⑤ 만)
    python3 scripts/audit_attribution_freshness.py --sample 40

P0 발견 시 exit 1 — 크론이 실패로 보고하게 한다. 발견 0 이면 exit 0.
관련: [[feedback_verify_by_load_bearing_not_surprise]] · [[feedback_measurement_audit_automation]]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(_ROOT, "data")
UA = "VERITY audit (gywns0126@gmail.com)"
SEC_DELAY = 0.13          # SEC 10 req/s 안전 마진
KST = timezone(timedelta(hours=9))

# 이 배율을 넘으면 제출인 기입 오류로 본다. 2026-08-15 실측 분포 = 정상 연중 변동 2~3배,
# 오류는 44배~82,541배로 명확히 갈린다. 20배는 그 사이 빈 구간이다.
UNIT_OUTLIER_FACTOR = 20.0
# 내부자 순증감이 발행주식의 이 비율을 넘으면 오귀속 의심. 지배주주 블록딜이 30%대까지
# 나오므로(INIO 13.8% 정상) 넉넉히 둔다. VWAV 오귀속은 14,000% 였다.
INSIDER_PCT_CEILING = 60.0
MAP_MAX_AGE_DAYS = 45     # 이름맵 30일 주기 + 유예 15일


class Finding:
    def __init__(self, sev: str, check: str, msg: str, detail: str = "") -> None:
        self.sev, self.check, self.msg, self.detail = sev, check, msg, detail

    def __str__(self) -> str:
        s = f"[{self.sev}] {self.check} — {self.msg}"
        return s + (f"\n        {self.detail}" if self.detail else "")


def _load(name: str) -> Optional[Any]:
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return None
    finally:
        time.sleep(SEC_DELAY)


def _universe() -> set:
    """미장 유니버스. 빌더와 같은 소스를 쓴다 — 여기서만 다른 정의를 쓰면 감사가 거짓말한다."""
    uni = set()
    for f in ("us_universe_combined.json", "us_universe_sp1500.json"):
        d = _load(f)
        if isinstance(d, dict):
            for k in ("tickers", "stocks", "universe"):
                v = d.get(k)
                if isinstance(v, list):
                    uni |= {str(x.get("ticker") if isinstance(x, dict) else x) for x in v}
        elif isinstance(d, list):
            uni |= {str(x.get("ticker") if isinstance(x, dict) else x) for x in d}
    return {t for t in uni if t and t != "None"}


# ── ① 유니버스 이탈 화석 ──────────────────────────────────────────────────

def check_universe_orphans(uni: set) -> List[Finding]:
    """유니버스 밖 티커의 엔트리는 회전 수집이 방문하지 않아 **영구 잔존**한다.

    2026-08-15 실측: us_insider_trades 에 33종목. 그중 OLPX(-15.1억주)·EEX 는 옛 파서
    산출이라 `-abs(net_change)` 정렬의 1·2위 = 공개 탭 최상단을 고칠 수 없는 상태로
    차지하고 있었다. 파서를 고쳐도 안 바뀌는 게 이 계열의 핵심이다.
    """
    out: List[Finding] = []
    if len(uni) < 1000:
        return [Finding("WARN", "orphan", f"유니버스 {len(uni)}종목 — 하한 미달로 검사 skip")]
    # 🚨 심각도는 **그 파일이 값을 이월하는지**로 갈린다. 둘을 같은 등급으로 두면
    #    경보가 잡음이 되고, 잡음이 되면 아무도 안 본다.
    #      carry-forward 있음 → 옛 파서 산출이 그대로 살아남는다 = P0
    #      신선도 게이트만 있음 → 값은 사실이고 범위만 벗어난다 = WARN
    carry_forward = {"us_insider_trades.json", "us_form144.json", "us_major_holdings.json"}
    for fn in ("us_insider_trades.json", "us_form144.json", "us_major_holdings.json",
               "us_short_interest.json", "us_disclosure_feed.json"):
        d = _load(fn)
        st = (d or {}).get("stocks") if isinstance(d, dict) else None
        if not isinstance(st, list):
            continue
        orph = [s.get("ticker") for s in st if s.get("ticker") and s["ticker"] not in uni]
        if not orph:
            continue
        cf = fn in carry_forward
        out.append(Finding(
            "P0" if cf else "WARN", "orphan",
            f"{fn}: 유니버스 이탈 {len(orph)}종목"
            + (" (값 이월 = 옛 오답 영구 잔존)" if cf else " (신선도 게이트 있음 = 범위 밖일 뿐)"),
            ", ".join(sorted(map(str, orph))[:12]) + (" 외" if len(orph) > 12 else "")))
    return out


# ── ② Form 144 주당 환산 이상치 ──────────────────────────────────────────

def check_form144_units() -> List[Finding]:
    """제출인이 직접 적는 aggregate market value 의 기입 오류를 잡는다.

    🚨 판정 로직을 여기서 다시 짜지 않고 **빌더 함수를 그대로 import** 한다. 감사가 자기
    사본을 들고 있으면 둘이 갈라져서, 빌더는 거르는데 감사는 통과시키거나 그 반대가 된다
    — 감사가 거짓말하는 가장 흔한 형태다. 판정 기준 변경은 한 곳에서만 일어나야 한다.
    """
    d = _load("us_form144.json")
    st = (d or {}).get("stocks") if isinstance(d, dict) else None
    if not isinstance(st, list):
        return [Finding("WARN", "f144-unit", "us_form144.json 없음/형식 불일치")]
    try:
        # 빌더가 `api.builders.*` 절대 import 를 쓰므로 repo root 가 sys.path 에 있어야 한다.
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from api.builders.us_form144_public_builder import (  # noqa: E402
            _flag_implied_price_outliers as flag)
    except Exception as e:  # import 실패를 조용히 넘기면 검사가 통과로 둔갑한다
        return [Finding("WARN", "f144-unit", f"빌더 판정 함수 import 실패: {type(e).__name__}")]

    hits = []
    for s in st:
        ns = [dict(n) for n in (s.get("notices") or [])]   # 원본 비파괴
        flag(ns, ticker=str(s.get("ticker") or ""))
        for n in ns:
            if n.get("value_suspect"):
                hits.append(f"{s.get('ticker')} {n['value_suspect'].split(' — ')[0]}")
    if hits:
        return [Finding("P0", "f144-unit", f"주당 환산 이상치 {len(hits)}건 (제출인 기입 오류)",
                        " · ".join(hits[:6]) + (" 외" if len(hits) > 6 else ""))]
    return []


# ── ③ 내부자 순증감 규모 ─────────────────────────────────────────────────

def _shares_outstanding(cik: str) -> Optional[float]:
    t = _get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}"
             "/dei/EntityCommonStockSharesOutstanding.json")
    if not t:
        return None
    try:
        rows = list(json.loads(t)["units"].values())[0]
        return float(rows[-1]["val"]) if rows else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def check_insider_magnitude(sample: int) -> List[Finding]:
    """|순증감| 을 발행주식과 대조한다. 발행주식의 몇 배 = 오귀속의 지문이다.

    VWAV 실측: 발행 2,538만주에 순증감 244억주(14,000%). 원인은 VisionWave 가 **남의
    회사(SVRE)** 지분을 산 Form 4 가 자기 종목 거래로 실린 것 — 거래코드가 진짜 P 라서
    매매 필터로는 안 걸리고 **규모 대조만이 유일한 지문**이었다.
    """
    d = _load("us_insider_trades.json")
    st = (d or {}).get("stocks") if isinstance(d, dict) else None
    if not isinstance(st, list):
        return [Finding("WARN", "insider-mag", "us_insider_trades.json 없음/형식 불일치")]
    top = sorted(st, key=lambda s: -abs(int(s.get("net_change") or 0)))[:sample]
    out, unchecked = [], 0
    for s in top:
        cik = str(s.get("cik") or "").zfill(10)
        net = abs(int(s.get("net_change") or 0))
        if not cik.strip("0") or net == 0:
            continue
        so = _shares_outstanding(cik)
        if not so:
            unchecked += 1
            continue
        pct = net / so * 100
        if pct > INSIDER_PCT_CEILING:
            out.append(Finding("P0", "insider-mag",
                               f"{s.get('ticker')}: 순증감 {net:,}주 = 발행주식의 {pct:,.0f}%",
                               "오귀속(남의 발행사 Form 4) 또는 단위 오류 의심"))
    if unchecked:
        # 🚨 조용한 축소 금지 — 못 본 만큼을 신고한다.
        out.append(Finding("WARN", "insider-mag",
                           f"발행주식 조회 실패 {unchecked}/{len(top)}종목 — 그만큼 미검사"))
    return out


# ── ④ 발행사 귀속 표본 대조 ──────────────────────────────────────────────

def check_issuer_attribution(sample: int) -> List[Finding]:
    """Form 4 원문의 issuer CIK 가 우리가 붙인 종목인지 표본 대조한다.

    EDGAR 는 같은 서식을 발행사 CIK 와 신고자 CIK **양쪽에** 색인한다. 발행사 확인 없이
    수집하면 '우리 종목이 남의 내부자로서 낸 공시' 가 자기 거래로 실린다.
    """
    d = _load("us_insider_trades.json")
    st = (d or {}).get("stocks") if isinstance(d, dict) else None
    if not isinstance(st, list):
        return []
    top = sorted(st, key=lambda s: -abs(int(s.get("net_change") or 0)))[:sample]
    out, checked = [], 0
    for s in top:
        tr = (s.get("trades") or [])
        if not tr:
            continue
        url = str(tr[0].get("source_url") or "")
        if "/Archives/edgar/data/" not in url:
            continue
        base = url.rsplit("/", 1)[0]
        idx = _get(base + "/index.json")
        if not idx:
            continue
        try:
            items = json.loads(idx)["directory"]["item"]
        except (ValueError, KeyError, TypeError):
            continue
        xml_name = next((i["name"] for i in items if i["name"].endswith(".xml")), None)
        if not xml_name:
            continue
        raw = _get(f"{base}/{xml_name}")
        if not raw:
            continue
        try:
            iss = ET.fromstring(raw).find(".//issuer")
            icik = (iss.findtext("issuerCik") or "").lstrip("0") if iss is not None else ""
        except ET.ParseError:
            continue
        checked += 1
        our = str(int(str(s.get("cik") or "0") or 0))
        if icik and icik != our:
            sym = (iss.findtext("issuerTradingSymbol") or "?") if iss is not None else "?"
            out.append(Finding("P0", "issuer-attr",
                               f"{s.get('ticker')}: 공시 발행사가 {sym}(CIK {icik}) — 우리 종목 아님",
                               f"원문 {base}/{xml_name}"))
    if checked == 0:
        out.append(Finding("WARN", "issuer-attr", "표본 0건 대조 — 네트워크·구조 변경 확인 필요"))
    return out


# ── ⑤ 이름맵 신선도 ──────────────────────────────────────────────────────

def _git_last_commit_days(path: str) -> Optional[float]:
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%ct", "--", path],
                           cwd=_ROOT, capture_output=True, text=True, timeout=20)
        ts = r.stdout.strip()
        return (time.time() - float(ts)) / 86400 if ts else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def check_map_freshness() -> List[Finding]:
    """이름맵 3종의 신선도.

    🚨 **파일 mtime 을 쓰지 않는다.** CI 는 매 run 마다 새로 체크아웃해서 mtime 이 항상
    '방금' 이다 — 실제로 이 함정 때문에 30일 갱신 게이트가 CI 에서 한 번도 발동하지
    않았고(2026-08-15 발견), 맵이 2개월 넘게 고정돼 신규 상장이 누락됐다.
    판정은 ① 사이드카의 생성 시각 ② git 커밋 이력 — 둘 다 체크아웃에 영향받지 않는다.
    """
    out: List[Finding] = []
    meta = _load("kr_name_map_meta.json")
    if not meta or not meta.get("generated_at"):
        out.append(Finding("WARN", "map-fresh",
                           "kr_name_map_meta.json 부재 — 다음 파이프라인 run 이 재빌드(정상)"))
    else:
        try:
            born = datetime.fromisoformat(str(meta["generated_at"]))
            if born.tzinfo is None:
                born = born.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - born).days
            if age > MAP_MAX_AGE_DAYS:
                out.append(Finding("P0", "map-fresh",
                                   f"이름맵 생성 후 {age}일 (상한 {MAP_MAX_AGE_DAYS}일)",
                                   "30일 갱신 게이트가 발동하지 않고 있다"))
        except (ValueError, TypeError):
            out.append(Finding("WARN", "map-fresh", "kr_name_map_meta.json generated_at 파싱 실패"))

    for f in ("data/kr_listed.json", "data/kr_stock_names.json"):
        days = _git_last_commit_days(f)
        if days is not None and days > MAP_MAX_AGE_DAYS:
            out.append(Finding("P0", "map-fresh",
                               f"{f}: 마지막 커밋 {days:.0f}일 전",
                               "생성은 되는데 커밋이 안 되거나, 갱신 자체가 안 도는 상태"))
    return out


# ── ⑥ 13D/G 커버리지 ────────────────────────────────────────────────────

def check_13dg_coverage(sample: int) -> List[Finding]:
    """EDGAR 실제 13D/G 건수 대비 우리 포착률.

    🚨 죽은 폼명 필터를 잡는 검사다. EDGAR 는 같은 서식을 `SC 13G`(구형)와
    `SCHEDULE 13G`(신형) 두 표기로 반환하는데, 한쪽만 등록해 두면 **최근 상장·최근
    공시일수록 포착률이 0 에 수렴**한다(2026-08-15 실측: SPCX 4건 전량 누락).
    커버리지가 얇을 땐 소스가 아니라 우리 수집기 필터부터 본다
    ([[feedback_coverage_check_collector_filter_first]]).
    """
    d = _load("us_major_holdings.json")
    st = (d or {}).get("stocks") if isinstance(d, dict) else None
    if not isinstance(st, list):
        return [Finding("WARN", "13dg-cov", "us_major_holdings.json 없음/형식 불일치")]
    ours = {s.get("ticker"): s for s in st if s.get("ticker")}
    # 보유 건수 상위 = 실제 13D/G 가 많은 종목. 여기서 0 이면 필터가 죽은 것이다.
    probe = sorted(st, key=lambda s: -(s.get("total") or 0))[:sample]
    out, zero = [], []
    for s in probe:
        cik = str(s.get("cik") or "").zfill(10)
        if not cik.strip("0"):
            continue
        t = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if not t:
            continue
        try:
            forms = json.loads(t)["filings"]["recent"]["form"]
        except (ValueError, KeyError, TypeError):
            continue
        edgar_n = sum(1 for f in forms if "13D" in f.upper() or "13G" in f.upper())
        our_n = int(s.get("total") or 0)
        if edgar_n >= 5 and our_n == 0:
            zero.append(f"{s.get('ticker')}: EDGAR {edgar_n}건 vs 우리 0건")
        elif edgar_n >= 10 and our_n < edgar_n * 0.2:
            zero.append(f"{s.get('ticker')}: EDGAR {edgar_n}건 vs 우리 {our_n}건")
    if zero:
        out.append(Finding("P0", "13dg-cov", f"포착률 이상 {len(zero)}종목 (폼명 필터 의심)",
                           " · ".join(zero[:6])))
    return out


# ── 실행 ─────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-net", action="store_true", help="SEC 실호출 없이 파일·git 검사만")
    ap.add_argument("--sample", type=int, default=25, help="실호출 검사 표본 상한")
    a = ap.parse_args()

    print(f"# 귀속·신선도 감사 — {datetime.now(KST).isoformat(timespec='seconds')}")
    uni = _universe()
    print(f"  유니버스 {len(uni)}종목 · 표본 상한 {a.sample} · 네트워크 {'off' if a.no_net else 'on'}\n")

    findings: List[Finding] = []
    findings += check_universe_orphans(uni)
    findings += check_form144_units()
    findings += check_map_freshness()
    if not a.no_net:
        findings += check_insider_magnitude(a.sample)
        findings += check_issuer_attribution(a.sample)
        findings += check_13dg_coverage(a.sample)
    else:
        print("  [skip] ③내부자규모 ④발행사귀속 ⑥13D/G커버리지 — --no-net\n")

    p0 = [f for f in findings if f.sev == "P0"]
    warn = [f for f in findings if f.sev != "P0"]
    for f in p0 + warn:
        print(str(f))
    print()
    print(f"결과: P0 {len(p0)}건 · WARN {len(warn)}건")
    if p0:
        print("🚨 P0 = 값이 조용히 틀린 상태. 에러·경보가 0 이라 이 검사 말고는 탐지 경로가 없다.")
        return 1
    if not findings:
        print("발견 0 — 검사 6종 통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
